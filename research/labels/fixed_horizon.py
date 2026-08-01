"""Fixed-horizon forward mid returns, streaming, on the local clock.

For a sample at time ``t`` with entry mid ``m0`` (the last mid strictly
before ``t``), the label at horizon ``h`` is the return to the last mid
observed at or before ``t + h`` — never a mid from the future side of the
deadline. Labels resolve as the stream passes each deadline, so memory is
bounded by the samples in flight within the longest horizon. Samples whose
horizon extends past the end of the stream are censored (``None``), not
truncated to a shorter horizon.

The horizon at which predictability dies is itself a finding worth
reporting, which is why all horizons are computed for every sample.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

NS_PER_MS = 1_000_000
DEFAULT_HORIZONS_MS: tuple[int, ...] = (100, 500, 1_000, 5_000, 30_000)


class FixedHorizonLabeler:
    """Resolves forward mid returns (bps) per horizon as the stream advances."""

    def __init__(self, horizons_ms: tuple[int, ...] = DEFAULT_HORIZONS_MS) -> None:
        self.horizons_ms = horizons_ms
        # Per horizon: FIFO of (deadline_ns, sample_index, entry_mid).
        self._pending: dict[int, deque[tuple[int, int, float]]] = {h: deque() for h in horizons_ms}
        self._last_mid: float | None = None

    def on_sample(self, index: int, t_ns: int, entry_mid: float) -> None:
        for horizon_ms, queue in self._pending.items():
            queue.append((t_ns + horizon_ms * NS_PER_MS, index, entry_mid))

    def on_mid(self, ts_ns: int, mid: float) -> list[tuple[int, int, float]]:
        """Advance the clock; returns resolved ``(index, horizon_ms, ret_bps)``.

        Deadlines strictly before ``ts_ns`` resolve against the previous mid
        (the last one at or before the deadline); a deadline exactly at
        ``ts_ns`` resolves against this mid.
        """
        resolved: list[tuple[int, int, float]] = []
        if self._last_mid is not None:
            resolved.extend(self._resolve(lambda deadline: deadline < ts_ns, self._last_mid))
        self._last_mid = mid
        resolved.extend(self._resolve(lambda deadline: deadline <= ts_ns, mid))
        return resolved

    def _resolve(
        self, is_due: Callable[[int], bool], exit_mid: float
    ) -> list[tuple[int, int, float]]:
        out: list[tuple[int, int, float]] = []
        for horizon_ms, queue in self._pending.items():
            while queue and is_due(queue[0][0]):
                _, index, entry_mid = queue.popleft()
                out.append((index, horizon_ms, 1e4 * (exit_mid - entry_mid) / entry_mid))
        return out

    def finalize(self) -> list[tuple[int, int]]:
        """Indices/horizons censored by end of stream — labels stay ``None``."""
        censored = [
            (index, horizon_ms)
            for horizon_ms, queue in self._pending.items()
            for _, index, _ in queue
        ]
        for queue in self._pending.values():
            queue.clear()
        return censored
