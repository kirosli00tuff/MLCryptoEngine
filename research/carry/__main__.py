"""CLI: ``python -m research.carry`` — the whole C.11 study.

Order is the order the report reads in: what the sample covers, what funding
paid and how often it did not, what the two-leg trade netted on deployed
capital, and what would have broken it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from data.archive import binance, binance_futures
from data.archive import hyperliquid as hl
from data.archive import series as bar_series
from data.config import AppConfig, load_config
from research.carry import funding as fx
from research.carry import risk as rk
from research.carry import trade as tr
from research.validation.experiment_log import log_experiment

COINS = (
    "BTC",
    "ETH",
    "HYPE",
    "SOL",
    "PUMP",
    "DOT",
    "LINK",
    "ARB",
    "GMX",
    "MERL",
    "TNSR",
    "NOT",
)
SPOT_PERIOD_START = "2023-05"
SPOT_PERIOD_END = "2026-07"
# Binance perpetuals for the decay question: Hyperliquid launched in 2023-05 and
# cannot show whether the yield was richer before that.
DECAY_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DECAY_START = "2019-09"
# The benchmark a carry has to beat. Doing nothing is not zero — cash earns
# something, and a trade carrying liquidation tail risk has to clear that first.
RISK_FREE_PCT = 4.0
# The rebalancing band is the whole design trade-off, so it is swept rather
# than chosen: a tight band bounds the capital requirement and pays the 40 bps
# spot leg to do it, a loose one saves the cost and lets margin grow without
# limit. Picking one band would present a preference as a result.
REBALANCE_BANDS = (0.02, 0.05, 0.10, 0.25, 0.50)
MS_PER_NS = 1_000_000
MS_PER_HOUR = 3_600_000


def _spot_series(cfg: AppConfig, coin: str) -> dict[int, float]:
    """Hourly Binance spot closes keyed by epoch millisecond."""
    periods = binance.months_between(SPOT_PERIOD_START, SPOT_PERIOD_END)
    bars = bar_series.load_symbol(cfg, f"{coin}USDT", "1h", periods)
    return {ns // MS_PER_NS: bar.close for ns, bar in bars.items()}


def _align(
    rows: list[hl.FundingRow], spot: dict[int, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Line funding up with spot on the hour they share.

    The perp price is reconstructed as ``spot * (1 + premium)`` from
    Hyperliquid's own mark-to-index premium, because the venue's candle
    endpoint serves only the most recent ~5,000 bars — 208 days at hourly
    resolution — and cannot cover the sample.
    """
    times, spots, perps, rates, premia = [], [], [], [], []
    for row in rows:
        hour_ms = row.time_ms - (row.time_ms % MS_PER_HOUR)
        price = spot.get(hour_ms)
        if price is None or not price > 0 or not np.isfinite(row.premium):
            continue
        times.append(hour_ms)
        spots.append(price)
        perps.append(price * (1.0 + row.premium))
        rates.append(row.rate)
        premia.append(row.premium)
    if len(times) < 24 * 30:
        return None
    return (
        np.asarray(times, dtype=np.int64),
        np.asarray(spots, dtype=np.float64),
        np.asarray(perps, dtype=np.float64),
        np.asarray(rates, dtype=np.float64),
        np.asarray(premia, dtype=np.float64),
    )


def _decay(cfg: AppConfig) -> dict[str, Any]:
    """Binance funding back to 2019 — has the yield been competed away?"""
    out: dict[str, Any] = {}
    periods = binance.months_between(DECAY_START, SPOT_PERIOD_END)
    for symbol in DECAY_SYMBOLS:
        for period in periods:
            binance_futures.fetch_funding_month(cfg, symbol, period)
        rows = binance_futures.load_funding(cfg, symbol, DECAY_START, SPOT_PERIOD_END)
        if not rows:
            continue
        by_year: dict[str, list[float]] = {}
        for row in rows:
            year = datetime.fromtimestamp(row.time_ms / 1000, tz=UTC).strftime("%Y")
            by_year.setdefault(year, []).append(row.rate)
        per_year = binance_futures.FUNDING_INTERVALS_PER_YEAR
        out[symbol] = {
            "observations": len(rows),
            "first": rk.stamp(rows[0].time_ms),
            "last": rk.stamp(rows[-1].time_ms),
            "annualised_pct_all": round(
                100 * sum(r.rate for r in rows) / (len(rows) / per_year), 2
            ),
            "yearly_annualised_pct": {
                year: round(100 * sum(v) / (len(v) / per_year), 2)
                for year, v in sorted(by_year.items())
                if len(v) > 100
            },
        }
    return out


def run(cfg: AppConfig) -> dict[str, Any]:
    config = tr.CarryConfig()
    per_coin: dict[str, Any] = {}
    results: list[tr.CarryResult] = []

    for coin in COINS:
        rows = hl.fetch_funding(cfg, coin)
        if not rows:
            per_coin[coin] = {"error": "no funding history"}
            continue
        stats = fx.characterise(coin, rows)
        entry: dict[str, Any] = {"funding": stats.summary()}

        aligned = _align(rows, _spot_series(cfg, coin))
        if aligned is None:
            entry["trade"] = {
                "error": (
                    f"no overlapping hourly spot series for {coin}USDT — the asset has no "
                    "Binance spot listing, so the long leg cannot be priced here"
                )
            }
            per_coin[coin] = entry
            continue

        times, spots, perps, rates, premia = aligned
        result = tr.simulate(coin, times, spots, perps, rates, config)
        if result is None:
            entry["trade"] = {"error": "series too short to simulate"}
            per_coin[coin] = entry
            continue

        sweep = []
        for band in REBALANCE_BANDS:
            variant = tr.simulate(
                coin, times, spots, perps, rates, tr.CarryConfig(rebalance_band=band)
            )
            if variant is not None:
                sweep.append(
                    {
                        "band_pct": round(100 * band, 1),
                        "rebalances_per_year": variant.row()["rebalances_per_year"],
                        "rebalance_cost_pct": variant.row()["rebalance_cost_pct"],
                        "capital_per_notional": variant.row()["capital_per_unit_entry_notional"],
                        "net_pct_of_capital_pa": variant.row()["net_pct_of_capital_pa"],
                    }
                )
        held = tr.simulate(coin, times, spots, perps, rates, tr.CarryConfig(reset_to_target=False))
        results.append(result)
        found = rk.negative_funding_risk(stats.negative_runs, config)
        entry["trade"] = result.row()
        entry["trade_buy_and_hold"] = held.row() if held else None
        entry["band_sweep"] = sweep
        entry["best_band"] = max(sweep, key=lambda r: r["net_pct_of_capital_pa"]) if sweep else None
        entry["regime"] = fx.regime_correlation(
            rows, dict(zip(times.tolist(), spots.tolist(), strict=True))
        )
        entry["negative_funding_risk"] = found.summary() if found else None
        entry["basis_risk"] = rk.basis_risk(premia)
        entry["liquidation_risk"] = rk.liquidation_risk(spots, config)
        entry["leverage_sweep"] = rk.leverage_sweep(spots)
        per_coin[coin] = entry

    positive = [r for r in results if r.annualised_on_capital > 0]
    beats_cash = [r for r in results if 100 * r.annualised_on_capital > RISK_FREE_PCT]
    rows_out = [r.row() for r in results]
    return {
        "premise": (
            "Carry, not prediction: long spot, short perp, collect funding. No model, "
            "no features, no labels — almost none of the Phase B research layer applies."
        ),
        "sample": {
            "venue": "Hyperliquid perpetuals (the only shortable venue reachable from BC)",
            "funding_interval": "hourly since 2023-06-08; eight-hourly for the 27 days before",
            "first_possible": "2023-05-12 (venue launch)",
            "spot_leg_prices": (
                "Binance spot 1h (free archive); the tradeable long leg is Kraken or "
                "Coinbase, which the basis section bounds"
            ),
            "perp_price_construction": (
                "spot x (1 + Hyperliquid premium) — the venue's candle endpoint serves "
                "only the most recent ~5,000 bars and cannot cover the sample"
            ),
        },
        "cost_model": config.describe(),
        "risk_free_benchmark_pct": RISK_FREE_PCT,
        "coins": per_coin,
        "aggregate": {
            "instruments_modelled": len(results),
            "positive_net_on_capital": len(positive),
            "beating_risk_free": len(beats_cash),
            "best": (max(rows_out, key=lambda r: r["net_pct_of_capital_pa"]) if rows_out else None),
            "worst": (
                min(rows_out, key=lambda r: r["net_pct_of_capital_pa"]) if rows_out else None
            ),
        },
        "binance_decay": _decay(cfg),
        "unmodellable_risks": rk.unmodellable_risks(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.carry")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON payload here")
    args = parser.parse_args(argv)

    cfg = load_config()
    payload = run(cfg)

    log_experiment(
        {
            "stage": "C.11",
            "study": "funding rate carry, delta-neutral long spot / short perp",
            "source": "hyperliquid_info + binance_futures_archive (kind=archive, free)",
            "dates": [payload["sample"]["first_possible"], "2026-08-04"],
            "cost_summary": json.dumps(payload["cost_model"]),
            "results": payload["aggregate"],
            "note": "carry trade, not a machine learning strategy; no model was fitted",
        }
    )

    text = json.dumps(payload, indent=1, default=str)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
