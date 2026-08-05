"""Dollar-neutral cross-sectional carry: construction, cost, and what is left over.

The trade: at each rebalance, rank every instrument the venue was funding that
day by its trailing funding rate, go long the bottom decile and short the top
decile, equal dollars a side. Both legs are Hyperliquid perps at 1.5 bps maker,
so unlike C.11 there is no 40 bps spot leg to dominate the cost stack — and
unlike C.11, both legs *receive* funding, since a long collects when funding is
negative and a short collects when it is positive.

**Dollar neutral is not delta neutral, and this module exists to measure the
difference.** C.11's structure cancelled price exposure mechanically: the same
asset, long and short, equal units, leaving only the perp's premium to index —
basis points. Nothing cancels here. The long basket is one set of coins and the
short basket a different set, and they can move apart without limit. That
residual is not a risk to be bounded, it is a term in the P&L, and a positive
total built from a small carry and a large directional bet is a directional bet.

Price return and funding income are therefore accumulated **separately** and
combined only at the end. :func:`residual_price_risk` reports the realised
correlation between the two baskets and the book's beta to BTC, because those
are what decide which of the two things this is.

**Three modelling choices worth stating.**

*Funding accrues on the notional the position carried into the day*, not on its
closing notional, matching C.11's convention. Crediting funding on a notional
that has already grown attributes part of the day's price move to the carry.

*A delisting is a forced exit, not a hole.* A held instrument that stops being
priced is closed at the last price the venue printed and charged one side of
fees. That is a modelling assumption — the venue settles delisted perps at an
oracle price this study cannot see — and it is why a delisted name costs
something here instead of silently vanishing at its entry price.

*Capital is the peak margin the path ever demanded* (ADR-035). Both legs are
margined on the same venue, a genuine structural advantage over C.11 where the
spot leg consumed its full notional on a second venue. Reporting return on
notional would flatter this trade by the same factor it would have flattered
that one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from research.cross import universe as uni

BPS = 1e-4
# Hyperliquid perps, base-tier maker, per side. config/venues.yaml
# hyperliquid.fee_tiers, verified 2026-08-01: 0.015% maker / 0.045% taker.
# C.9 measured the round trip at 3.0 bps.
FEE_BPS_PER_SIDE = 1.5
# Margin as a fraction of gross notional. 0.5 is 2x leverage, matching C.11's
# deliberately conservative choice: the tail risk in a levered book is
# liquidation, and this sample contains no bear market to test it against.
MARGIN_FRACTION = 0.5
# Doing nothing is not zero. C.11 benchmarked against cash and so does this.
RISK_FREE_PCT = 4.0
MIN_DAYS_FOR_STATS = 30


@dataclass(frozen=True)
class CrossConfig:
    """Every sizing and cost assumption in one place, all stated."""

    fee_bps_per_side: float = FEE_BPS_PER_SIDE
    lookback_days: int = 7
    rebalance_days: int = 7
    # 0 means decile sizing: one tenth of the live cross-section a side.
    names_per_side: int = 0
    margin_fraction: float = MARGIN_FRACTION
    gross_notional: float = 20_000.0
    min_cross_section: int = 10
    # A coin needs this fraction of the lookback observed before it can be
    # ranked, so a two-day-old listing cannot win the screen on one wild print.
    min_signal_coverage: float = 0.5

    def side_count(self, live: int) -> int:
        if self.names_per_side > 0:
            return max(1, min(self.names_per_side, live // 2))
        return max(1, live // 10)

    def describe(self) -> dict[str, Any]:
        return {
            "venue": "Hyperliquid perps, both legs",
            "fee_bps_per_side": self.fee_bps_per_side,
            "fee_source": (
                "config/venues.yaml hyperliquid.fee_tiers base tier, maker 1.5 bps, "
                "verified 2026-08-01 against the venue's published schedule. Hyperliquid "
                "tiers are 14-day weighted volume with HYPE-staking discounts, so only "
                "the base tier is modelled (ADR-012: fee schedules are perishable)."
            ),
            "no_spot_leg": (
                "C.11's 40 bps/side spot leg does not exist in this structure; both legs "
                "are perps on one venue"
            ),
            "lookback_days": self.lookback_days,
            "rebalance_days": self.rebalance_days,
            "sizing": (
                f"{self.names_per_side} names a side"
                if self.names_per_side
                else "bottom and top decile of the live cross-section"
            ),
            "neutrality": "dollar-neutral (equal dollars long and short), NOT delta-neutral",
            "margin_fraction": self.margin_fraction,
            "gross_notional": self.gross_notional,
        }


@dataclass
class Simulation:
    """One run's realised path, kept as separate terms until the very end."""

    config: CrossConfig
    days: list[int] = field(default_factory=list)
    funding_pnl: float = 0.0
    price_pnl: float = 0.0
    cost: float = 0.0
    traded_notional: float = 0.0
    rebalances: int = 0
    forced_exits: int = 0
    # Days a held instrument had no price but was still listed. Distinct from a
    # forced exit and counted separately, because treating one as the other is
    # how a one-day publication hole becomes a phantom liquidation.
    gap_days: int = 0
    # per-day series, all aligned to ``days``
    equity: list[float] = field(default_factory=list)
    gross_notional: list[float] = field(default_factory=list)
    price_return: list[float] = field(default_factory=list)
    funding_return: list[float] = field(default_factory=list)
    long_return: list[float] = field(default_factory=list)
    short_return: list[float] = field(default_factory=list)
    peak_margin: float = 0.0
    turnover_per_rebalance: list[float] = field(default_factory=list)
    cross_section: list[int] = field(default_factory=list)

    @property
    def years(self) -> float:
        return len(self.days) / uni.DAYS_PER_YEAR

    @property
    def net_pnl(self) -> float:
        return self.funding_pnl + self.price_pnl - self.cost

    @property
    def deployed_capital(self) -> float:
        return max(self.peak_margin, self.config.margin_fraction * self.config.gross_notional)

    @property
    def max_drawdown(self) -> float:
        if not self.equity:
            return 0.0
        curve = np.asarray(self.equity, dtype=np.float64)
        peak = np.maximum.accumulate(curve)
        return float(np.min((curve - peak) / self.deployed_capital))

    @property
    def break_even_fee_bps(self) -> float:
        """Fee per side at which gross profit exactly pays for the trading.

        ADR-032 ranks strategies by this rather than by return, because it
        separates "the edge is smaller than the cost" from "there is no edge".
        A break-even far above 1.5 bps means cost is not the binding constraint
        and something else decides the trade.
        """
        gross = self.funding_pnl + self.price_pnl
        if self.traded_notional <= 0 or gross <= 0:
            return 0.0
        return gross / self.traded_notional / BPS

    def annualised(self, total: float) -> float:
        cap, years = self.deployed_capital, self.years
        return total / cap / years if cap > 0 and years > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        turns = np.asarray(self.turnover_per_rebalance or [0.0], dtype=np.float64)
        years = self.years
        return {
            "days": len(self.days),
            "years": round(years, 2),
            "first_day": uni.day_stamp(self.days[0]) if self.days else None,
            "last_day": uni.day_stamp(self.days[-1]) if self.days else None,
            "mean_cross_section_at_rebalance": round(
                float(np.mean(self.cross_section)) if self.cross_section else 0.0, 1
            ),
            # The three terms, separate. Combining them earlier is the error
            # this entire stage exists to avoid.
            "funding_income_pct_of_capital_pa": round(100 * self.annualised(self.funding_pnl), 2),
            "price_return_pct_of_capital_pa": round(100 * self.annualised(self.price_pnl), 2),
            "cost_pct_of_capital_pa": round(100 * self.annualised(-self.cost), 2),
            "net_pct_of_capital_pa": round(100 * self.annualised(self.net_pnl), 2),
            "net_pct_of_notional_pa": round(
                100 * self.net_pnl / self.config.gross_notional / years, 2
            )
            if years
            else 0.0,
            "capital_per_unit_gross_notional": round(
                self.deployed_capital / self.config.gross_notional, 3
            ),
            "deployed_capital": round(self.deployed_capital, 2),
            "gross_notional": self.config.gross_notional,
            "max_drawdown_pct_of_capital": round(100 * self.max_drawdown, 2),
            "rebalances": self.rebalances,
            "rebalances_per_year": round(self.rebalances / years, 1) if years else 0.0,
            "turnover_per_rebalance_pct_of_gross": round(100 * float(turns.mean()), 1),
            "annual_turnover_multiple_of_gross": round(
                self.traded_notional / self.config.gross_notional / years, 1
            )
            if years
            else 0.0,
            "traded_notional_total": round(self.traded_notional, 2),
            "break_even_fee_bps_per_side": round(self.break_even_fee_bps, 2),
            "modelled_fee_bps_per_side": self.config.fee_bps_per_side,
            "forced_exits_on_delisting": self.forced_exits,
            "held_days_with_no_price_still_listed": self.gap_days,
        }


def _signal(
    funding: dict[str, dict[int, float]], coin: str, window: list[int]
) -> tuple[float, int] | None:
    """Trailing mean daily funding over ``window``, and how many days it saw.

    ``window`` never contains a day later than the rebalance, so nothing here
    can see the return it is about to be ranked for.
    """
    seen = [funding[coin][d] for d in window if d in funding.get(coin, {})]
    if not seen:
        return None
    return float(np.mean(seen)), len(seen)


def simulate(
    funding: dict[str, dict[int, float]],
    price: dict[str, dict[int, float]],
    universe: uni.PerpUniverse,
    config: CrossConfig | None = None,
) -> Simulation:
    """Run the dollar-neutral cross-sectional carry over the whole sample.

    Positions are held in units, so a basket drifts with price between
    rebalances exactly as a real book would rather than being silently
    re-weighted every day for free.
    """
    cfg = config or CrossConfig()
    sim = Simulation(config=cfg)
    all_days = universe.days
    if len(all_days) <= cfg.lookback_days + cfg.rebalance_days:
        return sim

    units: dict[str, float] = {}
    # The price each open position was last marked at. Carried explicitly
    # rather than read from the previous day, so a hole in one instrument's
    # series cannot silently drop a day of its P&L.
    mark: dict[str, float] = {}
    start = cfg.lookback_days
    half_gross = cfg.gross_notional / 2.0

    for i in range(start, len(all_days)):
        day = all_days[i]

        # ---- mark the book through the day, on the notional it carried in ----
        day_price_pnl = day_funding_pnl = 0.0
        long_start = short_start = long_pnl = short_pnl = 0.0
        for coin, held in list(units.items()):
            open_px = mark[coin]
            notional = abs(held) * open_px
            close_px = price.get(coin, {}).get(day)
            if close_px is None:
                listing = universe.listings.get(coin)
                if listing is not None and day <= listing.last_day_ms:
                    # A publication hole in a still-listed instrument. Carry the
                    # mark forward; do not invent a price, and do not treat a
                    # missing print as a delisting.
                    sim.gap_days += 1
                    continue
                # Delisted mid-hold: exit at the last price the venue printed.
                sim.cost += notional * cfg.fee_bps_per_side * BPS
                sim.traded_notional += notional
                sim.forced_exits += 1
                del units[coin]
                del mark[coin]
                continue
            move = held * (close_px - open_px)
            mark[coin] = close_px
            day_price_pnl += move
            day_funding_pnl += -held * open_px * funding.get(coin, {}).get(day, 0.0)
            if held > 0:
                long_start += notional
                long_pnl += move
            else:
                short_start += notional
                short_pnl += -move  # the short leg's P&L, not the coin's move

        gross_start = long_start + short_start
        sim.price_pnl += day_price_pnl
        sim.funding_pnl += day_funding_pnl
        sim.days.append(day)
        sim.gross_notional.append(gross_start)
        sim.price_return.append(day_price_pnl / gross_start if gross_start > 0 else 0.0)
        sim.funding_return.append(day_funding_pnl / gross_start if gross_start > 0 else 0.0)
        sim.long_return.append(long_pnl / long_start if long_start > 0 else 0.0)
        sim.short_return.append(short_pnl / short_start if short_start > 0 else 0.0)
        sim.equity.append(sim.net_pnl)
        sim.peak_margin = max(sim.peak_margin, cfg.margin_fraction * gross_start - sim.net_pnl)

        # ---- rebalance on schedule, ranking only on what today already knows ----
        if (i - start) % cfg.rebalance_days:
            continue
        window = all_days[max(0, i - cfg.lookback_days) : i + 1]
        need = max(1, int(cfg.min_signal_coverage * len(window)))
        scored: list[tuple[float, str]] = []
        for coin in universe.members[day]:
            if day not in price.get(coin, {}):
                continue
            found = _signal(funding, coin, window)
            if found is not None and found[1] >= need:
                scored.append((found[0], coin))
        sim.cross_section.append(len(scored))
        if len(scored) < cfg.min_cross_section:
            continue

        scored.sort()
        per_side = cfg.side_count(len(scored))
        each = half_gross / per_side
        target = {coin: each for _, coin in scored[:per_side]}
        target.update({coin: -each for _, coin in scored[-per_side:]})

        traded = 0.0
        for coin in set(units) | set(target):
            held_notional = units.get(coin, 0.0) * mark.get(coin, 0.0)
            traded += abs(target.get(coin, 0.0) - held_notional)
        sim.cost += traded * cfg.fee_bps_per_side * BPS
        sim.traded_notional += traded
        sim.turnover_per_rebalance.append(traded / cfg.gross_notional)
        sim.rebalances += 1
        units = {coin: dollars / price[coin][day] for coin, dollars in target.items()}
        mark = {coin: price[coin][day] for coin in target}

    # Unwind whatever is still open, so the last position is not free to exit.
    closing = sum(abs(u) * mark.get(c, 0.0) for c, u in units.items())
    sim.cost += closing * cfg.fee_bps_per_side * BPS
    sim.traded_notional += closing
    if sim.equity:
        sim.equity[-1] = sim.net_pnl
    return sim


def _benchmark_returns(days: list[int], benchmark: dict[int, float]) -> np.ndarray:
    """Daily benchmark returns aligned to ``days``; NaN where a close is absent."""
    out = np.full(len(days), np.nan, dtype=np.float64)
    for i in range(1, len(days)):
        prev, now = benchmark.get(days[i - 1]), benchmark.get(days[i])
        if prev and now and prev > 0:
            out[i] = now / prev - 1.0
    return out


def _corr(a: np.ndarray, b: np.ndarray) -> float | None:
    keep = np.isfinite(a) & np.isfinite(b)
    if int(keep.sum()) < MIN_DAYS_FOR_STATS:
        return None
    if float(a[keep].std()) == 0.0 or float(b[keep].std()) == 0.0:
        return None
    return round(float(np.corrcoef(a[keep], b[keep])[0, 1]), 3)


def residual_price_risk(sim: Simulation, benchmark: dict[int, float]) -> dict[str, Any]:
    """Is this a carry trade with a residual, or a directional bet with a carry?

    Dollar neutrality equalises the *dollars* on each side and nothing else. If
    the two baskets are poorly correlated, or the book carries a real beta to
    the market, the price term is an independent bet the funding spread was
    never asked to justify.
    """
    if len(sim.days) < MIN_DAYS_FOR_STATS:
        return {"error": f"only {len(sim.days)} days simulated"}

    long_r = np.asarray(sim.long_return, dtype=np.float64)
    # The short basket's own price move, with the position's sign taken back
    # out, so the correlation compares two baskets of coins rather than a
    # basket against a position in one.
    short_px = -np.asarray(sim.short_return, dtype=np.float64)
    port_r = np.asarray(sim.price_return, dtype=np.float64)
    bench_r = _benchmark_returns(sim.days, benchmark)

    beta = r_squared = None
    keep = np.isfinite(port_r) & np.isfinite(bench_r)
    if int(keep.sum()) >= MIN_DAYS_FOR_STATS and float(bench_r[keep].std()) > 0:
        slope, intercept = np.polyfit(bench_r[keep], port_r[keep], 1)
        beta = round(float(slope), 3)
        residual = port_r[keep] - (slope * bench_r[keep] + intercept)
        total = float(((port_r[keep] - port_r[keep].mean()) ** 2).sum())
        r_squared = round(1.0 - float((residual**2).sum()) / total, 3) if total > 0 else None

    years = sim.years or 1.0
    price_total = float(np.prod(1.0 + port_r) - 1.0)
    funding_total = float(np.sum(sim.funding_return))
    return {
        "corr_long_basket_vs_short_basket_price": _corr(long_r, short_px),
        "beta_to_btc": beta,
        "r_squared_vs_btc": r_squared,
        "price_only_return_pct_of_gross_total": round(100 * price_total, 2),
        "price_only_return_pct_of_gross_pa": round(100 * price_total / years, 2),
        "funding_only_return_pct_of_gross_pa": round(100 * funding_total / years, 2),
        "price_return_daily_vol_pct": round(100 * float(np.std(port_r, ddof=1)), 3),
        "funding_return_daily_vol_pct": round(100 * float(np.std(sim.funding_return, ddof=1)), 3),
        "long_basket_price_pa_pct": round(100 * (float(np.prod(1.0 + long_r)) - 1.0) / years, 2),
        "short_basket_price_pa_pct": round(100 * (float(np.prod(1.0 + short_px)) - 1.0) / years, 2),
        "interpretation": (
            "Dollar-neutral equalises dollars, not risk. A |beta| well away from zero, or "
            "a long/short basket correlation well below 1.0, means the price term is an "
            "independent bet that the funding spread never justified."
        ),
    }


def by_year(sim: Simulation) -> dict[str, dict[str, Any]]:
    """Funding and price per calendar year, kept apart.

    A whole-sample annualisation hides which regime produced it, and this
    sample contains no bear market to average against.
    """
    buckets: dict[str, list[int]] = {}
    for idx, day in enumerate(sim.days):
        buckets.setdefault(uni.year_of(day), []).append(idx)
    capital = sim.deployed_capital
    out: dict[str, dict[str, Any]] = {}
    for year, idxs in sorted(buckets.items()):
        gross = np.asarray([sim.gross_notional[i] for i in idxs], dtype=np.float64)
        fund = np.asarray([sim.funding_return[i] for i in idxs], dtype=np.float64) * gross
        px = np.asarray([sim.price_return[i] for i in idxs], dtype=np.float64) * gross
        years = len(idxs) / uni.DAYS_PER_YEAR
        out[year] = {
            "days": len(idxs),
            "funding_pct_of_capital_pa": round(100 * float(fund.sum()) / capital / years, 2),
            "price_pct_of_capital_pa": round(100 * float(px.sum()) / capital / years, 2),
            "gross_pct_of_capital_pa": round(
                100 * float(fund.sum() + px.sum()) / capital / years, 2
            ),
        }
    return out


def worst_windows(sim: Simulation, window_days: int = 30) -> dict[str, Any]:
    """The worst rolling stretch, which an average return never shows."""
    if len(sim.days) <= window_days:
        return {"error": "sample shorter than the window"}
    gross = np.asarray(sim.gross_notional, dtype=np.float64)
    daily = (
        np.asarray(sim.funding_return, dtype=np.float64)
        + np.asarray(sim.price_return, dtype=np.float64)
    ) * gross
    rolled = np.convolve(daily, np.ones(window_days), mode="valid")
    worst, best = int(np.argmin(rolled)), int(np.argmax(rolled))
    capital = sim.deployed_capital
    return {
        "window_days": window_days,
        "worst_window_start": uni.day_stamp(sim.days[worst]),
        "worst_window_pct_of_capital": round(100 * float(rolled[worst]) / capital, 2),
        "best_window_start": uni.day_stamp(sim.days[best]),
        "best_window_pct_of_capital": round(100 * float(rolled[best]) / capital, 2),
        "note": "gross of costs, which are charged at rebalance rather than daily",
    }
