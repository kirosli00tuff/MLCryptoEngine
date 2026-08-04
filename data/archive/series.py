"""Raw monthly ZIPs into aligned price series, with continuity checked.

Two hazards live between a folder of kline files and a matrix a cointegration
test can consume, and both are silent.

**Symbol reuse.** A ticker is not an asset. ``LUNAUSDT`` has an unbroken run of
monthly files from 2020-08 to 2026-07, but the Terra collapse in May 2022 ended
one asset and Terra 2.0 started another on the same ticker — the old chain
became ``LUNCUSDT``. Read naively the series is continuous; in truth it is two
assets spliced together at a point where the price fell by roughly four orders
of magnitude and then restarted. No cointegration test interprets that
correctly, and none of them complain either: the splice looks like a structural
break, and a structural break looks like a relationship that decayed.

The same shape appears in redenominations (``BTTUSDT`` -> ``BTTCUSDT``, January
2022, a 1:1000 conversion). The detector is deliberately blunt — a single-bar
move beyond a factor of five — because on a top-sixty asset that is never an
ordinary market move, and because subtle detectors for this class of defect
fail subtly.

**Ragged coverage.** Members die mid-sample by design (ADR-029), so the matrix
is not rectangular. Series are aligned on a shared UTC index and absent
observations stay absent rather than being forward-filled: filling a dead
asset's price forward invents a flat series, and flat series are trivially
cointegrated with each other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from data.archive import binance
from data.config import AppConfig

# A single-bar close-to-close move beyond this factor on a top-sixty asset is a
# redenomination, a ticker reuse, or a bad print — never a market move. Five
# sits well above real crypto volatility (the worst genuine single-day moves in
# this sample are near 2x) and far below the thousand-fold jumps that
# redenominations produce, so the classification is never marginal.
DISCONTINUITY_FACTOR = 5.0
MAX_LOG_JUMP = math.log(DISCONTINUITY_FACTOR)


@dataclass(frozen=True)
class Discontinuity:
    """One suspected splice in a price series."""

    symbol: str
    date: str
    previous_close: float
    close: float

    @property
    def factor(self) -> float:
        return self.close / self.previous_close if self.previous_close > 0 else float("inf")

    def describe(self) -> str:
        return (
            f"{self.symbol} {self.date}: {self.previous_close:.8g} -> {self.close:.8g} "
            f"({self.factor:.4g}x in one bar)"
        )


@dataclass
class PriceMatrix:
    """Closes aligned on one index; NaN where an asset had no bar."""

    dates_ns: np.ndarray
    symbols: list[str]
    closes: np.ndarray  # shape (len(dates_ns), len(symbols))
    excluded: dict[str, str] = field(default_factory=dict)
    discontinuities: list[Discontinuity] = field(default_factory=list)

    def column(self, symbol: str) -> np.ndarray:
        return self.closes[:, self.symbols.index(symbol)]

    def overlap(self, left: str, right: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Index and closes for the bars where *both* symbols have an observation."""
        a, b = self.column(left), self.column(right)
        keep = np.isfinite(a) & np.isfinite(b)
        return self.dates_ns[keep], a[keep], b[keep]

    def observations(self, symbol: str) -> int:
        return int(np.isfinite(self.column(symbol)).sum())


def date_str(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, tz=UTC).strftime("%Y-%m-%d")


def load_symbol(
    cfg: AppConfig, symbol: str, interval: str, periods: list[str]
) -> dict[int, binance.Bar]:
    """Every cached bar for one symbol, keyed by bar-open nanosecond.

    Reads only what is already on disk; downloading is
    :func:`data.archive.universe.fetch_history`'s job, so loading can never
    reach the network by surprise.
    """
    out: dict[int, binance.Bar] = {}
    for period in periods:
        path = binance.month_path(cfg, symbol, interval, period)
        if not path.is_file() or path.stat().st_size == 0:
            continue
        for bar in binance.read_month(path):
            out[bar.open_ns] = bar
    return out


def find_discontinuities(symbol: str, bars: dict[int, binance.Bar]) -> list[Discontinuity]:
    """Single-bar moves beyond :data:`DISCONTINUITY_FACTOR`, in bar order."""
    found: list[Discontinuity] = []
    previous: binance.Bar | None = None
    for key in sorted(bars):
        bar = bars[key]
        if (
            previous is not None
            and previous.close > 0.0
            and bar.close > 0.0
            and abs(math.log(bar.close / previous.close)) > MAX_LOG_JUMP
        ):
            found.append(
                Discontinuity(
                    symbol=symbol,
                    date=date_str(bar.open_ns),
                    previous_close=previous.close,
                    close=bar.close,
                )
            )
        previous = bar
    return found


def build_matrix(
    cfg: AppConfig,
    symbols: list[str],
    interval: str,
    periods: list[str],
    min_observations: int = 0,
) -> PriceMatrix:
    """Aligned close matrix over ``symbols``, spliced series excluded.

    A symbol with a detected discontinuity is dropped entirely rather than
    truncated at the splice. Truncation would keep whichever side happened to
    be longer and silently change which asset the symbol denotes partway
    through the study.
    """
    loaded: dict[str, dict[int, binance.Bar]] = {}
    excluded: dict[str, str] = {}
    all_breaks: list[Discontinuity] = []

    for symbol in symbols:
        bars = load_symbol(cfg, symbol, interval, periods)
        if not bars:
            excluded[symbol] = "no cached bars in range"
            continue
        breaks = find_discontinuities(symbol, bars)
        if breaks:
            all_breaks.extend(breaks)
            excluded[symbol] = "price series is spliced — " + "; ".join(
                b.describe() for b in breaks[:3]
            )
            continue
        if len(bars) < min_observations:
            excluded[symbol] = f"{len(bars)} observations < {min_observations} required"
            continue
        loaded[symbol] = bars

    kept = sorted(loaded)
    index = sorted({ns for bars in loaded.values() for ns in bars})
    dates_ns = np.asarray(index, dtype=np.int64)
    closes = np.full((len(index), len(kept)), np.nan, dtype=np.float64)
    position = {ns: i for i, ns in enumerate(index)}
    for column, symbol in enumerate(kept):
        for ns, bar in loaded[symbol].items():
            closes[position[ns], column] = bar.close

    return PriceMatrix(
        dates_ns=dates_ns,
        symbols=kept,
        closes=closes,
        excluded=excluded,
        discontinuities=all_breaks,
    )
