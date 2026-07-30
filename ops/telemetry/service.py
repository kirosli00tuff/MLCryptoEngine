"""Telemetry service: probe every venue on a schedule, persist, repeat."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import time

import httpx
import structlog

from data.config import load_config
from data.logsetup import configure_logging
from ops.telemetry.probe import PercentileWindow, probe_once
from ops.telemetry.store import TelemetryStore


async def run_service() -> None:
    """Probe until SIGINT/SIGTERM; one Parquet flush + JSON update per cycle."""
    cfg = load_config()
    configure_logging(cfg.logs_dir / "telemetry.log", cfg.log_level)
    log = structlog.get_logger("telemetry")

    store = TelemetryStore(cfg.processed_dir, cfg.logs_dir)
    windows = {venue: PercentileWindow(cfg.telemetry.window) for venue in cfg.venues}

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info(
        "telemetry_starting",
        venues=sorted(cfg.venues),
        interval_s=cfg.telemetry.interval_s,
    )
    async with httpx.AsyncClient(http2=False) as client:
        while not stop.is_set():
            cycle_start = time.time_ns()
            for venue, vcfg in sorted(cfg.venues.items()):
                rtt_ms, ok, error = await probe_once(
                    client, vcfg.rest_status_url, cfg.telemetry.timeout_s
                )
                window = windows[venue]
                if ok:
                    window.add(rtt_ms)
                store.add(
                    {
                        "ts_ns": time.time_ns(),
                        "venue": venue,
                        "rtt_ms": round(rtt_ms, 3),
                        "ok": ok,
                        "error": error,
                        "p50_ms": round(window.p50, 3),
                        "p95_ms": round(window.p95, 3),
                        "p99_ms": round(window.p99, 3),
                    }
                )
                log.info(
                    "probe",
                    venue=venue,
                    rtt_ms=round(rtt_ms, 1),
                    ok=ok,
                    error=error,
                    p50_ms=round(window.p50, 1),
                    p95_ms=round(window.p95, 1),
                    p99_ms=round(window.p99, 1),
                )
            store.flush_parquet()
            store.write_latest_json()
            elapsed_s = (time.time_ns() - cycle_start) / 1e9
            wait_s = max(cfg.telemetry.interval_s - elapsed_s, 0.1)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=wait_s)
    store.flush_parquet()
    store.write_latest_json()
    log.info("telemetry_stopped")
