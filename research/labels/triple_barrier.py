"""Triple-barrier labels, streaming, with volatility-scaled barriers.

Reference: Lopez de Prado, *Advances in Financial Machine Learning* (2018),
ch. 3. A sample at time ``t`` with entry mid ``m0`` sets a profit target at
``m0 · (1 + pt_mult · sigma)`` and a stop at ``m0 · (1 - sl_mult · sigma)`` where sigma
is recent realized volatility (as a fraction, supplied by the caller from the
feature engine's trailing window — computed strictly before ``t``). The
label is +1 if the upper barrier is touched first, -1 for the lower, and 0
if the time limit expires untouched. Resolution is streaming: barriers are
checked as mids arrive, so memory is bounded by samples in flight within the
time limit.

Samples with no usable volatility estimate are refused (``on_sample`` returns
False) rather than labeled against a made-up barrier width.
"""

from __future__ import annotations

from dataclasses import dataclass

NS_PER_MS = 1_000_000


@dataclass(frozen=True, slots=True)
class BarrierOutcome:
    index: int
    label: int  # +1 profit target, -1 stop, 0 time limit
    ret_bps: float  # mid return at resolution, in bps of entry


@dataclass(slots=True)
class _Active:
    index: int
    entry_mid: float
    upper: float
    lower: float
    deadline_ns: int


class TripleBarrierLabeler:
    """Streams mids through active barriers and emits outcomes."""

    def __init__(
        self,
        pt_mult: float = 2.0,
        sl_mult: float = 2.0,
        time_limit_ms: int = 30_000,
    ) -> None:
        if pt_mult <= 0 or sl_mult <= 0 or time_limit_ms <= 0:
            raise ValueError("barrier multiples and time limit must be positive")
        self._pt_mult = pt_mult
        self._sl_mult = sl_mult
        self._limit_ns = time_limit_ms * NS_PER_MS
        self._active: list[_Active] = []
        self._last_mid: float | None = None

    def on_sample(self, index: int, t_ns: int, entry_mid: float, vol_fraction: float) -> bool:
        """Arm barriers for one sample; False when volatility is unusable."""
        if vol_fraction <= 0 or entry_mid <= 0:
            return False
        self._active.append(
            _Active(
                index=index,
                entry_mid=entry_mid,
                upper=entry_mid * (1 + self._pt_mult * vol_fraction),
                lower=entry_mid * (1 - self._sl_mult * vol_fraction),
                deadline_ns=t_ns + self._limit_ns,
            )
        )
        return True

    def on_mid(self, ts_ns: int, mid: float) -> list[BarrierOutcome]:
        resolved: list[BarrierOutcome] = []
        still_active: list[_Active] = []
        for item in self._active:
            if ts_ns > item.deadline_ns:
                # Timeout resolves against the last mid observed at-or-before
                # the deadline — this call's mid can be arbitrarily far past
                # it when the book goes quiet, and using it would let the
                # label encode movement beyond the declared time limit. An
                # item surviving to this call had deadline >= the previous
                # mid's timestamp, so _last_mid is exactly that mid.
                exit_mid = self._last_mid if self._last_mid is not None else item.entry_mid
                timeout_ret = 1e4 * (exit_mid - item.entry_mid) / item.entry_mid
                resolved.append(BarrierOutcome(item.index, 0, timeout_ret))
                continue
            ret_bps = 1e4 * (mid - item.entry_mid) / item.entry_mid
            if mid >= item.upper:
                resolved.append(BarrierOutcome(item.index, 1, ret_bps))
            elif mid <= item.lower:
                resolved.append(BarrierOutcome(item.index, -1, ret_bps))
            else:
                still_active.append(item)
        self._active = still_active
        self._last_mid = mid
        return resolved

    def finalize(self) -> list[int]:
        """Indices censored by end of stream — labels stay ``None``."""
        censored = [item.index for item in self._active]
        self._active = []
        return censored
