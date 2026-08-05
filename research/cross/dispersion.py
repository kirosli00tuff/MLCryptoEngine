"""The gate: has cross-sectional funding dispersion decayed the way level did?

C.11 established that the funding *level* has been competed away — Binance BTC
annualised 30.61% in 2021 and 1.94% in 2026, down roughly 85% from peak. A
cross-sectional strategy does not care about the level. Long the coins paying
the most negative funding and short the coins paying the most positive, and the
level cancels; what is left is the **spread between instruments**. C.11
measured that spread at a single moment and found it enormous — TNSR at -32.41%
annualised against HYPE at +21.60%, 54 points apart on one venue.

Dispersion and level are different quantities and either could have decayed
without the other. This module measures dispersion over the full sample so the
question is settled before anything is built on top of it. If dispersion has
compressed as severely as level did, the strategy is not viable now regardless
of what it would have earned historically, and the honest thing is to say so
and stop rather than construct an elaborate portfolio on a closed spread.

Three measures, because they fail differently:

**Decile spread** — top decile mean minus bottom decile mean. This is the
strategy's own gross edge before any cost, so it maps directly onto the trade.

**Standard deviation** — sensitive to the tails, which is both its use and its
weakness. A handful of pathological thin coins can hold it up while the
tradeable middle of the book compresses.

**Interquartile range** — robust to exactly those tails. If the IQR falls while
the standard deviation holds, dispersion has retreated into a few extreme names,
and the strategy then depends on those names being tradeable.

**The composition confound.** The venue listed 232 perps over the sample and
kept adding thinner ones, whose funding is wilder. Measured over all listed
instruments, dispersion could rise purely because the universe changed. Every
statistic here is therefore also computed on a **fixed cohort** — the
instruments already live at the cohort date — which holds composition constant
and answers whether dispersion decayed *within* a stable set of names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from research.cross import universe as uni

# Below this many instruments a "decile" is one name against one name, and the
# spread is a comparison of two coins rather than a cross-section. Thinner days
# are counted and excluded rather than quietly averaged in.
MIN_CROSS_SECTION = 10
PERCENTILE_LOW = 25.0
PERCENTILE_HIGH = 75.0
# A calendar year with fewer days than this is partial. Reading a trend off a
# few weeks of one regime is how a seasonal dip becomes a structural finding.
FULL_YEAR_DAYS = 300


@dataclass(frozen=True)
class DayDispersion:
    """One day's cross-sectional spread of annualised funding rates."""

    day_ms: int
    n: int
    tail_size: int
    mean: float
    decile_spread: float
    stdev: float
    iqr: float
    top_decile_mean: float
    bottom_decile_mean: float


def measure_day(day_ms: int, values: np.ndarray) -> DayDispersion | None:
    """Dispersion for one day, or ``None`` if there are too few instruments.

    ``values`` are annualised funding rates. Decile size is ``n // 10`` floored
    at one, and is carried on the result so a reader can see when "decile"
    meant two names.
    """
    n = int(values.size)
    if n < MIN_CROSS_SECTION:
        return None
    ordered = np.sort(values)
    tail = max(1, n // 10)
    bottom = float(ordered[:tail].mean())
    top = float(ordered[-tail:].mean())
    return DayDispersion(
        day_ms=day_ms,
        n=n,
        tail_size=tail,
        mean=float(values.mean()),
        decile_spread=top - bottom,
        stdev=float(values.std(ddof=1)),
        iqr=float(np.percentile(values, PERCENTILE_HIGH) - np.percentile(values, PERCENTILE_LOW)),
        top_decile_mean=top,
        bottom_decile_mean=bottom,
    )


def series(
    funding: dict[str, dict[int, float]],
    universe: uni.PerpUniverse,
    restrict_to: set[str] | None = None,
) -> tuple[list[DayDispersion], int]:
    """Daily dispersion over the sample, and how many days were too thin.

    ``restrict_to`` holds composition fixed — pass a cohort to separate
    "funding rates spread out" from "the venue listed wilder coins".
    """
    out: list[DayDispersion] = []
    skipped = 0
    for day in universe.days:
        coins = universe.members[day]
        if restrict_to is not None:
            coins = coins & restrict_to
        values = np.asarray(
            [funding[c][day] * uni.DAYS_PER_YEAR for c in coins if day in funding.get(c, {})],
            dtype=np.float64,
        )
        measured = measure_day(day, values)
        if measured is None:
            skipped += 1
        else:
            out.append(measured)
    return out, skipped


def by_year(days: list[DayDispersion]) -> dict[str, dict[str, Any]]:
    """Annual means of each daily statistic — the decay question, plainly.

    A mean of daily cross-sectional statistics rather than a statistic of the
    pooled year: pooling would blend cross-sectional spread with variation
    through time, and only the first is being asked about.
    """
    buckets: dict[str, list[DayDispersion]] = {}
    for day in days:
        buckets.setdefault(uni.year_of(day.day_ms), []).append(day)
    return {
        year: {
            "days": len(group),
            "mean_cross_section": round(float(np.mean([d.n for d in group])), 1),
            "mean_level_pct": round(100 * float(np.mean([d.mean for d in group])), 2),
            "decile_spread_pct": round(100 * float(np.mean([d.decile_spread for d in group])), 2),
            "stdev_pct": round(100 * float(np.mean([d.stdev for d in group])), 2),
            "iqr_pct": round(100 * float(np.mean([d.iqr for d in group])), 2),
            "top_decile_pct": round(100 * float(np.mean([d.top_decile_mean for d in group])), 2),
            "bottom_decile_pct": round(
                100 * float(np.mean([d.bottom_decile_mean for d in group])), 2
            ),
        }
        for year, group in sorted(buckets.items())
    }


def _decay(first: float, last: float) -> float | None:
    """Fall from ``first`` to ``last`` as a fraction, or ``None`` if undefined."""
    return None if first == 0.0 else round(1.0 - last / first, 3)


def verdict(
    all_days: list[DayDispersion], cohort_days: list[DayDispersion], skipped: int = 0
) -> dict[str, Any]:
    """Has dispersion decayed, and does the fixed cohort agree?

    Peak year is compared against the most recent **full** year rather than
    against the running one, and the partial year is reported separately rather
    than dropped — the same treatment C.11 gave its 2026 column.
    """
    annual, cohort_annual = by_year(all_days), by_year(cohort_days)
    years = sorted(annual)
    if len(years) < 2:
        return {"error": "fewer than two years of dispersion", "by_year": annual}

    spreads = {y: float(annual[y]["decile_spread_pct"]) for y in years}
    peak = max(spreads, key=lambda y: spreads[y])
    latest = years[-1]
    full_years = [y for y in years if int(annual[y]["days"]) >= FULL_YEAR_DAYS]
    anchor = full_years[-1] if full_years else latest
    partial = latest if latest not in full_years else None

    return {
        "by_year": annual,
        "by_year_fixed_cohort": cohort_annual,
        "days_below_min_cross_section": skipped,
        "min_cross_section": MIN_CROSS_SECTION,
        "peak_year": peak,
        "peak_decile_spread_pct": spreads[peak],
        "latest_full_year": anchor,
        "latest_full_year_decile_spread_pct": spreads[anchor],
        "partial_final_year": partial,
        "partial_final_year_decile_spread_pct": spreads[latest] if partial else None,
        "decile_spread_decay_from_peak": _decay(spreads[peak], spreads[anchor]),
        "decile_spread_decay_peak_to_partial": (
            _decay(spreads[peak], spreads[latest]) if partial else None
        ),
        "stdev_decay_from_peak": _decay(
            float(annual[peak]["stdev_pct"]), float(annual[anchor]["stdev_pct"])
        ),
        "iqr_decay_from_peak": _decay(
            float(annual[peak]["iqr_pct"]), float(annual[anchor]["iqr_pct"])
        ),
        "cohort_control": (
            "Dispersion recomputed on the instruments already live at the cohort date, "
            "holding universe composition fixed. If the all-instruments series is flat "
            "while this one falls, the flatness is the venue listing new coins rather "
            "than the spread persisting."
        ),
    }
