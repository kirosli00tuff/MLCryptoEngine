"""What funding actually paid, and how often it did not.

A carry trade's headline is an average, and an average is the least useful
statistic about a payment stream you have to sit inside. Four things decide
whether 14%/yr is a business or a mirage, and this module measures all four:

**Negative runs, not negative fraction.** A stream that is negative 30% of the
time in single hours is a rounding error; one that is negative 30% of the time
in three-week blocks is a margin call. The run-length distribution is the
statistic; the fraction alone is close to meaningless.

**Decay.** This is a crowded, widely published trade. If the yield is being
competed away then the trailing average overstates what is available now, and
that matters more than the average itself.

**Regime.** If funding only pays while price is rising, the standalone
annualised figure describes a leveraged long in disguise.

**Time-weighted annualisation.** Hyperliquid changed its funding interval from
eight-hourly to hourly on 2023-06-08, so no fixed intervals-per-year constant
is correct across this sample. Everything here divides accumulated funding by
elapsed time instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import numpy as np

from data.archive.hyperliquid import (
    MAX_CREDITED_INTERVAL_MS,
    MS_PER_YEAR,
    FundingRow,
    accumulated,
    annualised,
    elapsed_years,
    intervals_ms,
)

MS_PER_HOUR = 3_600_000
PERCENTILES = (1.0, 5.0, 25.0, 50.0, 75.0, 95.0, 99.0)
# A run of this many hours is a week. Anything longer has to be financed
# through a sustained loss rather than shrugged off.
LONG_RUN_HOURS = 168


@dataclass(frozen=True)
class NegativeRun:
    """One unbroken stretch where funding was paid rather than collected."""

    start_ms: int
    end_ms: int
    hours: float
    cost: float  # negative: fraction of notional surrendered over the run

    @property
    def start_date(self) -> str:
        return datetime.fromtimestamp(self.start_ms / 1000, tz=UTC).strftime("%Y-%m-%d")

    @property
    def annualised_while_running(self) -> float:
        years = self.hours / (24 * 365)
        return self.cost / years if years > 0 else 0.0


@dataclass
class FundingStats:
    """Everything the report says about one instrument's funding stream."""

    coin: str
    observations: int
    first_ms: int
    last_ms: int
    years: float
    accumulated: float
    annualised: float
    hourly_percentiles: dict[str, float] = field(default_factory=dict)
    negative_time_fraction: float = 0.0
    negative_runs: list[NegativeRun] = field(default_factory=list)
    yearly: dict[str, float] = field(default_factory=dict)
    decay_per_year: float = 0.0
    first_half_annualised: float = 0.0
    second_half_annualised: float = 0.0

    @property
    def worst_run(self) -> NegativeRun | None:
        return min(self.negative_runs, key=lambda r: r.cost, default=None)

    @property
    def longest_run(self) -> NegativeRun | None:
        return max(self.negative_runs, key=lambda r: r.hours, default=None)

    def summary(self) -> dict[str, Any]:
        worst, longest = self.worst_run, self.longest_run
        return {
            "coin": self.coin,
            "observations": self.observations,
            "first": datetime.fromtimestamp(self.first_ms / 1000, tz=UTC).strftime("%Y-%m-%d"),
            "last": datetime.fromtimestamp(self.last_ms / 1000, tz=UTC).strftime("%Y-%m-%d"),
            "years": round(self.years, 2),
            "accumulated_pct": round(100 * self.accumulated, 2),
            "annualised_pct": round(100 * self.annualised, 2),
            "annualised_percentiles_pct": {
                k: round(100 * v, 2) for k, v in self.hourly_percentiles.items()
            },
            "negative_time_pct": round(100 * self.negative_time_fraction, 1),
            "negative_runs": len(self.negative_runs),
            "runs_over_a_week": sum(1 for r in self.negative_runs if r.hours >= LONG_RUN_HOURS),
            "worst_run": (
                {
                    "start": worst.start_date,
                    "days": round(worst.hours / 24, 1),
                    "cost_pct": round(100 * worst.cost, 2),
                }
                if worst
                else None
            ),
            "longest_run": (
                {
                    "start": longest.start_date,
                    "days": round(longest.hours / 24, 1),
                    "cost_pct": round(100 * longest.cost, 2),
                }
                if longest
                else None
            ),
            "yearly_annualised_pct": {k: round(100 * v, 2) for k, v in self.yearly.items()},
            "decay_pct_per_year": round(100 * self.decay_per_year, 2),
            "first_half_pct": round(100 * self.first_half_annualised, 2),
            "second_half_pct": round(100 * self.second_half_annualised, 2),
        }


def _annualised_rate_series(rows: list[FundingRow]) -> np.ndarray:
    """Each row's rate expressed as an annual rate, using its own interval.

    A row covering eight hours at rate r annualises differently from an hourly
    row at the same r. Dividing by the row's realised interval is what makes
    the percentile table comparable across the venue's 2023-06-08 switch.
    """
    spans = np.asarray(intervals_ms(rows), dtype=np.float64)
    rates = np.asarray([r.rate for r in rows], dtype=np.float64)
    return np.where(spans > 0, rates * (MS_PER_YEAR / spans), 0.0)


def negative_runs(rows: list[FundingRow]) -> list[NegativeRun]:
    """Unbroken stretches of negative funding, with what each one cost.

    A single positive interval ends a run. That is deliberately strict: it
    makes the reported runs a *lower* bound on how long a position sits
    underwater, which is the conservative direction for a risk statistic.
    """
    runs: list[NegativeRun] = []
    spans = intervals_ms(rows)
    start_index: int | None = None
    cost = 0.0
    for i, row in enumerate(rows):
        if row.rate < 0.0:
            if start_index is None:
                start_index, cost = i, 0.0
            cost += row.rate
        elif start_index is not None:
            runs.append(
                NegativeRun(
                    start_ms=rows[start_index].time_ms,
                    end_ms=row.time_ms,
                    hours=sum(spans[start_index:i]) / MS_PER_HOUR,
                    cost=cost,
                )
            )
            start_index = None
    if start_index is not None:
        runs.append(
            NegativeRun(
                start_ms=rows[start_index].time_ms,
                end_ms=rows[-1].time_ms,
                hours=sum(spans[start_index:]) / MS_PER_HOUR,
                cost=cost,
            )
        )
    return runs


def yearly_annualised(rows: list[FundingRow]) -> dict[str, float]:
    """Annualised funding per calendar year — the decay question, plainly."""
    buckets: dict[str, list[FundingRow]] = {}
    for row in rows:
        year = datetime.fromtimestamp(row.time_ms / 1000, tz=UTC).strftime("%Y")
        buckets.setdefault(year, []).append(row)
    return {year: annualised(group) for year, group in sorted(buckets.items())}


def decay_slope(rows: list[FundingRow]) -> float:
    """Least-squares trend in annualised funding, per year of elapsed time.

    Negative means the yield is compressing. Fitted on the annualised series
    rather than raw rates, so the venue's interval change cannot masquerade as
    a trend.
    """
    if len(rows) < 3:
        return 0.0
    times = np.asarray([r.time_ms for r in rows], dtype=np.float64) / MS_PER_YEAR
    values = _annualised_rate_series(rows)
    times = times - times[0]
    design = np.column_stack([times, np.ones_like(times)])
    solution, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(solution[0])


def characterise(coin: str, rows: list[FundingRow]) -> FundingStats:
    """Full distributional description of one funding stream."""
    if not rows:
        raise ValueError(f"{coin}: no funding rows")
    spans = np.asarray(intervals_ms(rows), dtype=np.float64)
    per_year = _annualised_rate_series(rows)
    negative_ms = float(spans[np.asarray([r.rate < 0.0 for r in rows])].sum())

    half = len(rows) // 2
    stats = FundingStats(
        coin=coin,
        observations=len(rows),
        first_ms=rows[0].time_ms,
        last_ms=rows[-1].time_ms,
        years=elapsed_years(rows),
        accumulated=accumulated(rows),
        annualised=annualised(rows),
        negative_time_fraction=negative_ms / float(spans.sum()) if spans.sum() > 0 else 0.0,
        negative_runs=negative_runs(rows),
        yearly=yearly_annualised(rows),
        decay_per_year=decay_slope(rows),
        first_half_annualised=annualised(rows[:half]),
        second_half_annualised=annualised(rows[half:]),
    )
    stats.hourly_percentiles = {
        f"p{int(p)}": float(np.percentile(per_year, p)) for p in PERCENTILES
    }
    return stats


def regime_correlation(
    rows: list[FundingRow], prices_ms: dict[int, float], window_days: int = 30
) -> dict[str, Any]:
    """Does funding only pay while price is rising, or while it is calm?

    Both series are reduced to daily observations before correlating. Hourly
    funding against hourly returns would report a correlation dominated by
    microstructure noise, and the question here is about regimes.
    """
    by_day: dict[str, list[float]] = {}
    for row in rows:
        day = datetime.fromtimestamp(row.time_ms / 1000, tz=UTC).strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(row.rate)
    daily_funding = {day: sum(v) for day, v in by_day.items()}

    price_by_day: dict[str, float] = {}
    for ms in sorted(prices_ms):
        day = datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")
        price_by_day[day] = prices_ms[ms]  # last price of the day wins

    days = sorted(set(daily_funding) & set(price_by_day))
    if len(days) < 90:
        return {"error": f"only {len(days)} overlapping days"}

    funding = np.asarray([daily_funding[d] for d in days])
    prices = np.asarray([price_by_day[d] for d in days])
    returns = np.diff(np.log(prices), prepend=np.log(prices[0]))

    window = max(7, window_days)
    trend = np.full(len(days), np.nan)
    vol = np.full(len(days), np.nan)
    for i in range(window, len(days)):
        past = returns[i - window : i]
        trend[i] = float(past.sum())
        vol[i] = float(np.std(past, ddof=1)) * math.sqrt(365)

    keep = np.isfinite(trend) & np.isfinite(vol)
    if int(keep.sum()) < 30:
        return {"error": "too few windows"}

    def corr(a: np.ndarray, b: np.ndarray) -> float:
        if float(np.std(a)) == 0.0 or float(np.std(b)) == 0.0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    up = keep & (trend > 0)
    down = keep & (trend <= 0)
    return {
        "overlapping_days": len(days),
        "trend_window_days": window,
        "corr_funding_vs_trailing_trend": round(corr(funding[keep], trend[keep]), 3),
        "corr_funding_vs_realised_vol": round(corr(funding[keep], vol[keep]), 3),
        "mean_daily_funding_bps_uptrend": (
            round(1e4 * float(funding[up].mean()), 2) if int(up.sum()) else None
        ),
        "mean_daily_funding_bps_downtrend": (
            round(1e4 * float(funding[down].mean()), 2) if int(down.sum()) else None
        ),
        "uptrend_days": int(up.sum()),
        "downtrend_days": int(down.sum()),
    }


def gaps(rows: list[FundingRow]) -> list[tuple[int, int]]:
    """Publication holes: consecutive rows further apart than the credited max."""
    return [
        (a.time_ms, b.time_ms)
        for a, b in pairwise(rows)
        if b.time_ms - a.time_ms > MAX_CREDITED_INTERVAL_MS
    ]
