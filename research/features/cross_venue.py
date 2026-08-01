"""Cross-venue features on a common local clock.

Both venues are recorded by the same process on the same machine, so the
recorder's local receive timestamps form the one clock on which "Kraken knew
before Coinbase" is even a meaningful statement. Exchange timestamps are
never used here.

Features:
- ``xv_mid_diff_bps`` — primary venue mid minus reference venue mid, in bps
  of the reference mid.
- ``xv_diff_z`` — that divergence z-scored against its own trailing
  distribution (rolling mean/variance over a time window), so "unusually
  wide" is relative to recent behaviour, not an absolute threshold.
- ``xv_leadlag_<offset>`` — Pearson correlation between the primary venue's
  binned mid returns and the reference venue's returns shifted by ``offset``
  milliseconds. Positive offsets correlate the primary's return with the
  reference's *earlier* return: a peak at +100 ms means the reference venue
  leads by about 100 ms. Reference: Huth & Abergel (2014), "High frequency
  lead/lag relationships — empirical facts".
"""

from __future__ import annotations

import math
from itertools import pairwise

from research.features.rolling import WindowSum

NS_PER_MS = 1_000_000
MIN_LEADLAG_PAIRS = 30


class CrossVenueTracker:
    """Maintains both venues' mids and computes cross-venue features."""

    def __init__(
        self,
        bin_ms: int = 100,
        window_s: int = 30,
        z_window_s: int = 60,
        offsets_ms: tuple[int, ...] = (-500, -100, 0, 100, 500),
    ) -> None:
        self._bin_ns = bin_ms * NS_PER_MS
        self._window_bins = (window_s * 1000) // bin_ms
        self._offsets_bins = {off: (off * NS_PER_MS) // self._bin_ns for off in offsets_ms}
        self.offsets_ms = offsets_ms
        self._mids: dict[str, float] = {}
        self._bins: dict[str, dict[int, float]] = {"primary": {}, "reference": {}}
        self._diff_sum = WindowSum(z_window_s * 1_000_000_000)
        self._diff_sumsq = WindowSum(z_window_s * 1_000_000_000)

    def on_mid(self, role: str, ts_ns: int, mid: float) -> None:
        """Record a mid observation for ``role`` ("primary" or "reference")."""
        self._mids[role] = mid
        bins = self._bins[role]
        bin_idx = ts_ns // self._bin_ns
        bins[bin_idx] = mid
        for stale in [b for b in bins if b < bin_idx - self._window_bins]:
            del bins[stale]
        if role == "primary" and "reference" in self._mids:
            diff = self.mid_diff_bps()
            if diff is not None:
                self._diff_sum.add(ts_ns, diff)
                self._diff_sumsq.add(ts_ns, diff * diff)

    def mid_diff_bps(self) -> float | None:
        primary = self._mids.get("primary")
        reference = self._mids.get("reference")
        if primary is None or reference is None or reference <= 0:
            return None
        return 1e4 * (primary - reference) / reference

    def diff_zscore(self, now_ns: int) -> float | None:
        current = self.mid_diff_bps()
        count = self._diff_sum.count(now_ns)
        if current is None or count < MIN_LEADLAG_PAIRS:
            return None
        mean = self._diff_sum.total(now_ns) / count
        variance = self._diff_sumsq.total(now_ns) / count - mean * mean
        if variance <= 0:
            return None
        return (current - mean) / math.sqrt(variance)

    def _binned_returns(self, role: str) -> dict[int, float]:
        bins = self._bins[role]
        returns: dict[int, float] = {}
        ordered = sorted(bins)
        for prev_bin, curr_bin in pairwise(ordered):
            prev_mid, curr_mid = bins[prev_bin], bins[curr_bin]
            if prev_mid > 0 and curr_mid > 0:
                returns[curr_bin] = math.log(curr_mid / prev_mid)
        return returns

    def leadlag(self) -> dict[int, float | None]:
        """Correlation of primary returns with reference returns at each offset."""
        primary = self._binned_returns("primary")
        reference = self._binned_returns("reference")
        out: dict[int, float | None] = {}
        for offset_ms, offset_bins in self._offsets_bins.items():
            xs: list[float] = []
            ys: list[float] = []
            for bin_idx, primary_ret in primary.items():
                ref_ret = reference.get(bin_idx - offset_bins)
                if ref_ret is not None:
                    xs.append(primary_ret)
                    ys.append(ref_ret)
            out[offset_ms] = _pearson(xs, ys)
        return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < MIN_LEADLAG_PAIRS:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)
