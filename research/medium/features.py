"""Weekly feature panel with publication-lag gating as the load-bearing rule.

Everything here reduces to one mechanism: a feature observation is a
``(metric_date, value)`` pair, and a weekly decision row dated ``t`` may read
only the newest observation whose ``metric_date + lag_days <= t``. The lag is
per source, registered in progress.md (commit 370ba41), and where measurement
disagreed with the registered default the *measured* value won: the Coin
Metrics community snapshot retrieved 2026-08-06 ends 2026-05-23, so CM-derived
features carry a measured **75-day** lag rather than the +1 default. That is
what "freely available" actually means for this source, and pretending
otherwise is the exact lie medium-horizon on-chain backtests are built on.

Feature classes (the registered grid's rows):

- **A stablecoin** — market-wide net supply change over 7 and 28 days, and the
  z-score of the 7-day change against its trailing 90 days. Lag +1 day.
- **B exchange netflow** — per asset: 7-day net exchange flow (in minus out,
  USD) scaled by market cap, and the 28-day change in exchange-held supply.
  Lag +75 days, measured.
- **C funding regime** — per asset: trailing 7-day funding level annualised,
  its percentile in the trailing 365 days, and its 30-day slope. From this
  project's own archive; lag 0 (exchange-published at interval end).
- **D basis state** — per asset: 7-day mean Hyperliquid perp premium and its
  z-score against the trailing 90 days. Lag 0; the series begins 2023-05-12.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

MS_PER_DAY = 86_400_000
DAYS_PER_YEAR = 365
# Registered lags. B's is measured; the rest are documented/registered defaults.
LAG_DAYS = {"A": 1, "B": 75, "C": 0, "D": 0}


@dataclass(frozen=True)
class Series:
    """One daily metric as parallel arrays, sorted by metric date."""

    days_ms: np.ndarray
    values: np.ndarray

    @classmethod
    def from_map(cls, data: dict[int, float]) -> Series:
        keys = np.asarray(sorted(data), dtype=np.int64)
        return cls(days_ms=keys, values=np.asarray([data[int(k)] for k in keys], dtype=np.float64))

    def latest_usable(self, decision_ms: int, lag_days: int) -> float:
        """Newest value whose metric date + lag is at or before the decision."""
        cutoff = decision_ms - lag_days * MS_PER_DAY
        idx = int(np.searchsorted(self.days_ms, cutoff, side="right")) - 1
        return float(self.values[idx]) if idx >= 0 else math.nan

    def window_ending(self, metric_ms: int, days: int) -> np.ndarray:
        """Values with metric dates in ``(metric_ms - days, metric_ms]``."""
        lo = int(np.searchsorted(self.days_ms, metric_ms - days * MS_PER_DAY, side="right"))
        hi = int(np.searchsorted(self.days_ms, metric_ms, side="right"))
        return self.values[lo:hi]


def pct_change(series: Series, days: int) -> dict[int, float]:
    """Percent change over ``days``, dated at the window's END (a metric date)."""
    out: dict[int, float] = {}
    for i, day in enumerate(series.days_ms):
        j = int(np.searchsorted(series.days_ms, int(day) - days * MS_PER_DAY, side="right")) - 1
        if j < 0:
            continue
        base = series.values[j]
        if base != 0 and np.isfinite(base):
            out[int(day)] = float(series.values[i] / base - 1.0)
    return out


def rolling_z(values: dict[int, float], window_days: int) -> dict[int, float]:
    """Z-score of each observation against its own strictly-trailing window."""
    series = Series.from_map(values)
    out: dict[int, float] = {}
    for i, day in enumerate(series.days_ms):
        window = series.window_ending(int(day) - MS_PER_DAY, window_days)
        if window.size < 20:
            continue
        sigma = float(np.std(window, ddof=1))
        if sigma > 0:
            out[int(day)] = float((series.values[i] - float(np.mean(window))) / sigma)
    return out


def rolling_sum(values: dict[int, float], days: int) -> dict[int, float]:
    series = Series.from_map(values)
    return {int(day): float(series.window_ending(int(day), days).sum()) for day in series.days_ms}


def rolling_mean(values: dict[int, float], days: int, min_obs: int = 3) -> dict[int, float]:
    series = Series.from_map(values)
    out: dict[int, float] = {}
    for day in series.days_ms:
        window = series.window_ending(int(day), days)
        if window.size >= min_obs:
            out[int(day)] = float(np.mean(window))
    return out


def trailing_percentile(values: dict[int, float], window_days: int) -> dict[int, float]:
    series = Series.from_map(values)
    out: dict[int, float] = {}
    for i, day in enumerate(series.days_ms):
        window = series.window_ending(int(day) - MS_PER_DAY, window_days)
        if window.size >= 60:
            out[int(day)] = float(np.mean(window <= series.values[i]))
    return out


def slope(values: dict[int, float], days: int) -> dict[int, float]:
    """Value now minus value ``days`` ago, dated at the newer metric date."""
    series = Series.from_map(values)
    out: dict[int, float] = {}
    for i, day in enumerate(series.days_ms):
        j = int(np.searchsorted(series.days_ms, int(day) - days * MS_PER_DAY, side="right")) - 1
        if j >= 0:
            out[int(day)] = float(series.values[i] - series.values[j])
    return out


@dataclass
class FeatureSet:
    """Named daily feature maps for one class, plus the lag they carry."""

    klass: str
    lag_days: int
    features: dict[str, dict[int, float]] = field(default_factory=dict)

    def names(self) -> list[str]:
        return sorted(self.features)

    def row(self, decision_ms: int) -> list[float]:
        return [
            Series.from_map(self.features[name]).latest_usable(decision_ms, self.lag_days)
            for name in self.names()
        ]


def stablecoin_class(total_supply: dict[int, float]) -> FeatureSet:
    supply = Series.from_map(total_supply)
    chg7 = pct_change(supply, 7)
    return FeatureSet(
        klass="A",
        lag_days=LAG_DAYS["A"],
        features={
            "stbl_chg_7d": chg7,
            "stbl_chg_28d": pct_change(supply, 28),
            "stbl_chg7_z90": rolling_z(chg7, 90),
        },
    )


def netflow_class(
    flow_in_usd: dict[int, float],
    flow_out_usd: dict[int, float],
    mcap_usd: dict[int, float],
    sply_ex_ntv: dict[int, float],
) -> FeatureSet:
    """Exchange netflow, scaled so the number means the same thing across years."""
    net_daily = {
        day: flow_in_usd[day] - flow_out_usd[day] for day in set(flow_in_usd) & set(flow_out_usd)
    }
    net7 = rolling_sum(net_daily, 7)
    mcap = Series.from_map(mcap_usd)
    scaled: dict[int, float] = {}
    for day, value in net7.items():
        cap = mcap.latest_usable(day, 0)
        if np.isfinite(cap) and cap > 0:
            scaled[day] = value / cap
    return FeatureSet(
        klass="B",
        lag_days=LAG_DAYS["B"],
        features={
            "netflow7_over_mcap": scaled,
            "exsply_chg_28d": pct_change(Series.from_map(sply_ex_ntv), 28),
        },
    )


def funding_class(rates_8h: dict[int, float]) -> FeatureSet:
    """Funding regime from 8-hourly archive rows collapsed to daily sums."""
    daily: dict[int, float] = {}
    for time_ms, rate in rates_8h.items():
        day = time_ms - time_ms % MS_PER_DAY
        daily[day] = daily.get(day, 0.0) + rate
    level7 = {day: value * DAYS_PER_YEAR / 7.0 for day, value in rolling_sum(daily, 7).items()}
    return FeatureSet(
        klass="C",
        lag_days=LAG_DAYS["C"],
        features={
            "fund_level7_ann": level7,
            "fund_pctile_365": trailing_percentile(level7, 365),
            "fund_slope_30d": slope(level7, 30),
        },
    )


def basis_class(premium_hourly: dict[int, float]) -> FeatureSet:
    daily: dict[int, float] = {}
    counts: dict[int, int] = {}
    for time_ms, premium in premium_hourly.items():
        day = time_ms - time_ms % MS_PER_DAY
        daily[day] = daily.get(day, 0.0) + premium
        counts[day] = counts.get(day, 0) + 1
    prem7 = rolling_mean({day: daily[day] / counts[day] for day in daily}, 7)
    return FeatureSet(
        klass="D",
        lag_days=LAG_DAYS["D"],
        features={"prem_7d_mean": prem7, "prem_z90": rolling_z(prem7, 90)},
    )


def combined_names(parts: list[FeatureSet]) -> list[str]:
    names: list[str] = []
    for part in parts:
        names.extend(f"{part.klass}_{name}" for name in part.names())
    return names


def combined_row(parts: list[FeatureSet], decision_ms: int) -> list[float]:
    """Row for class E — each component read at its OWN lag, never a shared one."""
    row: list[float] = []
    for part in parts:
        row.extend(part.row(decision_ms))
    return row


def weekly_grid(start_ms: int, end_ms: int, weekday: int = 6) -> list[int]:
    """UTC week-end days (default Sunday) covering [start, end]."""
    out = []
    day = start_ms - start_ms % MS_PER_DAY
    while day <= end_ms:
        if (day // MS_PER_DAY + 3) % 7 == weekday:  # epoch day 0 was a Thursday
            out.append(day)
        day += MS_PER_DAY
    return out


def panel_summary(parts: list[FeatureSet]) -> dict[str, Any]:
    return {
        part.klass: {
            "lag_days": part.lag_days,
            "features": part.names(),
            "observations": {name: len(v) for name, v in part.features.items()},
        }
        for part in parts
    }
