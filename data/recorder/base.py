"""Venue-agnostic recorder core: connect, subscribe, capture, reconnect, report."""

from __future__ import annotations

import asyncio
import contextlib
import random
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import orjson
import structlog
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from data.config import AppConfig, VenueConfig
from data.recorder.gaps import GapLogger
from data.recorder.writer import RawFileWriter

OPEN_TIMEOUT_S = 10.0
PING_INTERVAL_S = 20.0
PING_TIMEOUT_S = 20.0
# Coinbase full-depth level2 snapshots exceed the websockets default of 1 MiB;
# a lossless recorder must never reject a frame for being large.
MAX_MESSAGE_BYTES = 64 * 1024 * 1024


class DryRunLimiter:
    """Shared budget of messages to print across all venues in --dry-run mode."""

    def __init__(self, limit: int) -> None:
        self._remaining = limit

    def take(self) -> bool:
        """Consume one print slot; False once the budget is spent."""
        if self._remaining <= 0:
            return False
        self._remaining -= 1
        return True

    @property
    def exhausted(self) -> bool:
        return self._remaining <= 0


@dataclass
class HeartbeatState:
    """Mutable liveness counters, read by the heartbeat emitter."""

    venue: str
    connected: bool = False
    messages_total: int = 0
    last_seq: int | None = None


class VenueRecorder(ABC):
    """One venue's capture loop. Subclasses supply subscriptions and sequence parsing."""

    venue_key: str = ""

    def __init__(
        self,
        venue_cfg: VenueConfig,
        app_cfg: AppConfig,
        writer: RawFileWriter,
        gaps: GapLogger,
        dry_run: DryRunLimiter | None = None,
    ) -> None:
        self.venue_cfg = venue_cfg
        self.settings = app_cfg.recorder
        self.writer = writer
        self.gaps = gaps
        self.heartbeat = HeartbeatState(venue=self.venue_key)
        self._dry_run = dry_run
        self._log = structlog.get_logger("recorder").bind(venue=self.venue_key)

    @abstractmethod
    def subscribe_messages(self) -> list[str]:
        """JSON payloads to send immediately after the socket opens."""

    @abstractmethod
    def sequence_of(self, message: dict[str, Any]) -> int | None:
        """Venue sequence number of a parsed message, if the venue provides one."""

    async def run(self, stop: asyncio.Event) -> None:
        """Capture until ``stop`` is set, reconnecting with jittered backoff."""
        attempt = 0
        disconnect_ns: int | None = None
        disconnect_reason = "startup"
        while not stop.is_set():
            try:
                async with connect(
                    self.venue_cfg.ws_url,
                    open_timeout=OPEN_TIMEOUT_S,
                    ping_interval=PING_INTERVAL_S,
                    ping_timeout=PING_TIMEOUT_S,
                    max_size=MAX_MESSAGE_BYTES,
                ) as ws:
                    reconnect_ns = time.time_ns()
                    if disconnect_ns is not None:
                        if self._dry_run is None:
                            gap = self.gaps.log_gap(disconnect_ns, reconnect_ns, disconnect_reason)
                            self._log.warning(
                                "gap_logged",
                                duration_ms=gap.duration_ms,
                                reason=disconnect_reason,
                            )
                        else:
                            # Dry-run records no market data, so it must not
                            # pollute the permanent gap sidecar either — a
                            # diagnostic mode stays out of the data plane.
                            self._log.warning(
                                "gap_not_logged_dry_run",
                                duration_ms=(reconnect_ns - disconnect_ns) // 1_000_000,
                                reason=disconnect_reason,
                            )
                        disconnect_ns = None
                    attempt = 0
                    await self._subscribe(ws)
                    self.heartbeat.connected = True
                    self._log.info("connected", url=self.venue_cfg.ws_url)
                    closer = asyncio.create_task(self._close_on_stop(ws, stop))
                    try:
                        await self._read_loop(ws, stop)
                    finally:
                        closer.cancel()
            except (OSError, WebSocketException, TimeoutError) as exc:
                if disconnect_ns is None:
                    disconnect_ns = time.time_ns()
                disconnect_reason = f"{type(exc).__name__}: {exc}"
                self._log.warning("disconnected", reason=disconnect_reason, attempt=attempt)
            finally:
                self.heartbeat.connected = False
            if stop.is_set():
                break
            await self._backoff(attempt, stop)
            attempt += 1

    async def _subscribe(self, ws: ClientConnection) -> None:
        for payload in self.subscribe_messages():
            await ws.send(payload)

    async def _read_loop(self, ws: ClientConnection, stop: asyncio.Event) -> None:
        async for frame in ws:
            recv_ns = time.time_ns()
            raw = frame if isinstance(frame, str) else frame.decode("utf-8", "backslashreplace")
            if self._dry_run is not None:
                if self._dry_run.take():
                    sys.stdout.write(raw + "\n")
                    sys.stdout.flush()
                if self._dry_run.exhausted:
                    stop.set()
                    return
            else:
                self.writer.write(recv_ns, raw)
            self._track(raw)
            if stop.is_set():
                return

    def _track(self, raw: str) -> None:
        self.heartbeat.messages_total += 1
        try:
            parsed = orjson.loads(raw)
        except orjson.JSONDecodeError:
            self._log.warning("unparseable_message", size=len(raw))
            return
        if isinstance(parsed, dict):
            seq = self.sequence_of(parsed)
            if seq is not None:
                self.heartbeat.last_seq = seq

    async def _backoff(self, attempt: int, stop: asyncio.Event) -> None:
        base = min(self.settings.backoff_max_s, self.settings.backoff_initial_s * (2**attempt))
        delay = base * (1 - self.settings.backoff_jitter * random.random())
        self._log.info("reconnect_backoff", delay_s=round(delay, 2), attempt=attempt)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=delay)

    @staticmethod
    async def _close_on_stop(ws: ClientConnection, stop: asyncio.Event) -> None:
        await stop.wait()
        await ws.close()
