"""Round-trip latency probing over the venues' public REST endpoints.

Measured RTTs feed Phase C backtests. Timeouts are recorded as failed samples
rather than dropped: losing the slow tail is exactly the mistake that makes a
constant-latency backtest overstate performance.
"""

from __future__ import annotations

import time
from collections import deque

import httpx


class PercentileWindow:
    """Rolling window of successful RTT samples with exact percentiles."""

    def __init__(self, size: int) -> None:
        self._samples: deque[float] = deque(maxlen=size)

    def add(self, rtt_ms: float) -> None:
        self._samples.append(rtt_ms)

    def __len__(self) -> int:
        return len(self._samples)

    def percentile(self, fraction: float) -> float:
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
        return ordered[index]

    @property
    def p50(self) -> float:
        return self.percentile(0.50)

    @property
    def p95(self) -> float:
        return self.percentile(0.95)

    @property
    def p99(self) -> float:
        return self.percentile(0.99)


async def probe_once(
    client: httpx.AsyncClient,
    url: str,
    timeout_s: float,
    method: str = "GET",
    json_body: dict[str, object] | None = None,
) -> tuple[float, bool, str | None]:
    """One RTT measurement: (rtt_ms, ok, error). Timeouts count with rtt=timeout.

    ``method``/``json_body`` exist for POST-only endpoints: Hyperliquid's info
    endpoint rejects GET with 405, so a GET there would measure the rejection
    path, not the request path an order-shaped POST traverses.
    """
    start = time.perf_counter()
    try:
        response = await client.request(method, url, json=json_body, timeout=timeout_s)
        rtt_ms = (time.perf_counter() - start) * 1000
    except httpx.HTTPError as exc:
        rtt_ms = (time.perf_counter() - start) * 1000
        return rtt_ms, False, f"{type(exc).__name__}: {exc}"
    if response.status_code >= 400:
        return rtt_ms, False, f"HTTP {response.status_code}"
    return rtt_ms, True, None
