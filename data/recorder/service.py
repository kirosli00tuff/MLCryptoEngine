"""Recorder service: run all venue recorders concurrently with liveness heartbeats."""

from __future__ import annotations

import asyncio
import contextlib
import signal

import structlog

from data.config import AppConfig, load_config
from data.logsetup import configure_logging
from data.recorder import RECORDER_TYPES
from data.recorder.base import DryRunLimiter, VenueRecorder
from data.recorder.gaps import GapLogger
from data.recorder.writer import RawFileWriter


def build_recorders(
    cfg: AppConfig,
    venue_keys: list[str],
    dry_run: DryRunLimiter | None,
) -> list[VenueRecorder]:
    """Instantiate one recorder per requested venue, validating keys against config."""
    unknown = [k for k in venue_keys if k not in cfg.venues]
    if unknown:
        known = ", ".join(sorted(cfg.venues))
        raise SystemExit(f"Unknown venue(s): {', '.join(unknown)}. Configured venues: {known}")
    unsupported = [k for k in venue_keys if k not in RECORDER_TYPES]
    if unsupported:
        supported = ", ".join(sorted(RECORDER_TYPES))
        raise SystemExit(
            f"No recorder implemented for: {', '.join(unsupported)}. Supported: {supported}"
        )
    recorders: list[VenueRecorder] = []
    for key in venue_keys:
        recorders.append(
            RECORDER_TYPES[key](
                venue_cfg=cfg.venues[key],
                app_cfg=cfg,
                writer=RawFileWriter(cfg.raw_dir, key),
                gaps=GapLogger(cfg.raw_dir, key),
                dry_run=dry_run,
            )
        )
    return recorders


async def _emit_heartbeats(
    recorders: list[VenueRecorder],
    interval_s: float,
    stop: asyncio.Event,
) -> None:
    log = structlog.get_logger("recorder")
    previous: dict[str, int] = {}
    while not stop.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        for recorder in recorders:
            total = recorder.heartbeat.messages_total
            rate = (total - previous.get(recorder.venue_key, 0)) / interval_s
            previous[recorder.venue_key] = total
            log.info(
                "heartbeat",
                venue=recorder.venue_key,
                connected=recorder.heartbeat.connected,
                msgs_total=total,
                msgs_per_s=round(rate, 2),
                raw_bytes_total=recorder.writer.raw_bytes_total,
                bytes_on_disk_hour=recorder.writer.bytes_on_disk_hour,
                last_seq=recorder.heartbeat.last_seq,
            )


async def run_service(venue_keys: list[str] | None, dry_run: bool) -> None:
    """Entry point: record the requested venues until SIGINT/SIGTERM (or dry-run end)."""
    cfg = load_config()
    configure_logging(cfg.logs_dir / "recorder.log", cfg.log_level)
    log = structlog.get_logger("recorder")

    keys = venue_keys if venue_keys else sorted(RECORDER_TYPES)
    limiter = DryRunLimiter(cfg.recorder.dry_run_messages) if dry_run else None
    recorders = build_recorders(cfg, keys, limiter)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info("recorder_starting", venues=keys, dry_run=dry_run)
    heartbeat_task = asyncio.create_task(
        _emit_heartbeats(recorders, cfg.recorder.heartbeat_interval_s, stop)
    )
    try:
        await asyncio.gather(*(r.run(stop) for r in recorders))
    finally:
        stop.set()
        await heartbeat_task
        for recorder in recorders:
            recorder.writer.close()
        log.info(
            "recorder_stopped",
            totals={r.venue_key: r.heartbeat.messages_total for r in recorders},
        )
