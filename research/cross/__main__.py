"""CLI: ``python -m research.cross`` — the whole C.13 study.

Order is the order the question has to be answered in, and it is deliberately
not the order that shows the strategy in its best light. Dispersion comes
first because it is the gate: if the cross-sectional spread has been competed
away the way C.11 showed the funding *level* was, then no amount of portfolio
construction recovers it, and an elaborate backtest on a closed spread is a way
of not noticing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from data.config import AppConfig, load_config
from research.cross import acquire, dispersion, portfolio, universe
from research.validation.experiment_log import log_experiment

BENCHMARK = "BTC"
# Cadences to sweep. Cross-sectional rank changes drive turnover and turnover
# drives cost, so the cadence is swept rather than chosen — the treatment C.11
# gave its rebalance bands. Picking one would present a preference as a result.
REBALANCE_DAYS = (1, 3, 7, 14, 30)
LOOKBACKS = (3, 7, 14, 30)
SIDE_COUNTS = (0, 3, 5, 10)  # 0 means decile sizing
# The fixed-cohort control starts once the venue has run long enough to have a
# cross-section at all.
COHORT_OFFSET_DAYS = 90


def _cohort_day(built: universe.PerpUniverse) -> int:
    days = built.days
    return days[min(COHORT_OFFSET_DAYS, len(days) - 1)]


def _sweep(
    funding: dict[str, dict[int, float]],
    price: dict[str, dict[int, float]],
    built: universe.PerpUniverse,
    variants: list[portfolio.CrossConfig],
    benchmark: dict[int, float],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cfg in variants:
        sim = portfolio.simulate(funding, price, built, cfg)
        if not sim.days:
            continue
        risk = portfolio.residual_price_risk(sim, benchmark)
        row = sim.summary()
        out.append(
            {
                "lookback_days": cfg.lookback_days,
                "rebalance_days": cfg.rebalance_days,
                "names_per_side": cfg.names_per_side or "decile",
                "turnover_per_rebalance_pct": row["turnover_per_rebalance_pct_of_gross"],
                "annual_turnover_x_gross": row["annual_turnover_multiple_of_gross"],
                "funding_pct_pa": row["funding_income_pct_of_capital_pa"],
                "price_pct_pa": row["price_return_pct_of_capital_pa"],
                "cost_pct_pa": row["cost_pct_of_capital_pa"],
                "net_pct_of_capital_pa": row["net_pct_of_capital_pa"],
                "max_drawdown_pct": row["max_drawdown_pct_of_capital"],
                "break_even_fee_bps": row["break_even_fee_bps_per_side"],
                "beta_to_btc": risk.get("beta_to_btc"),
            }
        )
    return out


def run(cfg: AppConfig, limit: int | None = None) -> dict[str, Any]:
    end_ms = int(time.time() * 1000)
    assets, histories = acquire.fetch_all(cfg, end_ms, limit=limit, verbose=False)
    built = universe.build(histories, assets)
    if not built.days:
        return {"error": "no usable instruments", "coverage": acquire.coverage(assets, histories)}

    funding, price = universe.panels(histories, built)
    benchmark = price.get(BENCHMARK, {})

    # ---- Task 2: the gate. Dispersion, before anything is built on top of it.
    cohort = universe.cohort_listed_by(built, _cohort_day(built))
    all_days, skipped = dispersion.series(funding, built)
    cohort_days, _ = dispersion.series(funding, built, restrict_to=cohort)
    gate = dispersion.verdict(all_days, cohort_days, skipped)
    gate["fixed_cohort_size"] = len(cohort)
    gate["fixed_cohort_start"] = universe.day_stamp(_cohort_day(built))

    # ---- Tasks 3-5: construction, cost, residual price risk, capital
    base = portfolio.CrossConfig()
    sim = portfolio.simulate(funding, price, built, base)
    risk = portfolio.residual_price_risk(sim, benchmark)

    variants = [portfolio.CrossConfig(rebalance_days=d) for d in REBALANCE_DAYS]
    variants += [portfolio.CrossConfig(lookback_days=lb) for lb in LOOKBACKS]
    variants += [portfolio.CrossConfig(names_per_side=n) for n in SIDE_COUNTS]

    summary = sim.summary()
    net_pa = float(summary["net_pct_of_capital_pa"])
    return {
        "premise": (
            "Cross-sectional funding carry: long the perps paying the most negative "
            "funding, short those paying the most positive, dollar-neutral, both legs on "
            "Hyperliquid. Unlike C.11 there is no spot leg and no 80 bps venue — and "
            "unlike C.11, nothing cancels the price exposure."
        ),
        "universe": built.summary(),
        "coverage": acquire.coverage(assets, histories),
        "dispersion_gate": gate,
        "cost_model": base.describe(),
        "result": summary,
        "residual_price_risk": risk,
        "by_year": portfolio.by_year(sim),
        "worst_30d": portfolio.worst_windows(sim, 30),
        "worst_90d": portfolio.worst_windows(sim, 90),
        "sweep": _sweep(funding, price, built, variants, benchmark),
        "benchmark": {
            "risk_free_pct": portfolio.RISK_FREE_PCT,
            "net_pct_of_capital_pa": net_pa,
            "beats_cash": bool(net_pa > portfolio.RISK_FREE_PCT),
            "excess_over_cash_pct": round(net_pa - portfolio.RISK_FREE_PCT, 2),
        },
        "regimes_absent": (
            "Hyperliquid launched 2023-05-12, after the 2022 drawdown, so no bear market "
            "sits inside this history at all. The sample holds the 2023 recovery, the 2024 "
            "bull run and the 2025-26 compression. Every figure here is drawn from a "
            "sample with no sustained decline in it, and a dollar-neutral book's price "
            "term is exactly what an untested regime would move."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.cross")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON payload here")
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N perps (development only)"
    )
    args = parser.parse_args(argv)

    payload = run(load_config(), limit=args.limit)
    gate = payload.get("dispersion_gate", {})
    log_experiment(
        {
            "stage": "C.13",
            "study": "cross-sectional funding carry, dollar-neutral perp/perp on Hyperliquid",
            "source": "hyperliquid_info (kind=archive, free, nothing purchased)",
            "dates": [
                payload.get("universe", {}).get("first_day"),
                payload.get("universe", {}).get("last_day"),
            ],
            "cost_summary": json.dumps(payload.get("cost_model", {})),
            "results": {
                "dispersion_gate": {
                    k: gate.get(k)
                    for k in (
                        "peak_year",
                        "peak_decile_spread_pct",
                        "latest_full_year",
                        "latest_full_year_decile_spread_pct",
                        "decile_spread_decay_from_peak",
                    )
                },
                "result": payload.get("result"),
                "residual_price_risk": payload.get("residual_price_risk"),
                "benchmark": payload.get("benchmark"),
            },
            "note": (
                "carry trade, not a machine learning strategy; no model fitted. "
                "Dollar-neutral, NOT delta-neutral: price exposure does not cancel."
            ),
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
