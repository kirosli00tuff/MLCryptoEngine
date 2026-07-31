"""Free-space guard for an always-on recorder.

Warns, and only warns. It never stops recording, never rotates early, and
never deletes anything: a disk that fills costs the tail of one day, whereas a
guard that reacts by stopping or pruning costs data that cannot be recaptured.
Recorded raw data is immutable (see CLAUDE.md), so the only correct automatic
response to low disk is a loud log line and a human decision.

Thresholds are configuration, not constants — a VPS sized for one venue and a
workstation holding months of capture want different numbers.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import structlog

BYTES_PER_GB = 1024**3
# While free space stays below a threshold, re-log at most this often. The
# first crossing is always logged immediately; this only throttles repeats so
# an overnight low-disk condition does not bury the heartbeat stream.
REPEAT_INTERVAL_S = 300.0


class DiskLevel(StrEnum):
    """Severity of the current free-space reading."""

    OK = "ok"
    LOW = "low"
    CRITICAL = "critical"


@dataclass(frozen=True)
class DiskStatus:
    """One free-space reading. Immutable; a new reading is a new object."""

    path: Path
    free_bytes: int
    total_bytes: int
    level: DiskLevel

    @property
    def free_gb(self) -> float:
        return self.free_bytes / BYTES_PER_GB

    @property
    def total_gb(self) -> float:
        return self.total_bytes / BYTES_PER_GB


def read_disk(path: Path, warn_free_gb: float, critical_free_gb: float) -> DiskStatus:
    """Free-space reading for the filesystem holding ``path``.

    Walks up to the nearest existing ancestor, so a data root that has not been
    created yet still reports the filesystem it will land on rather than
    raising.
    """
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    free_gb = usage.free / BYTES_PER_GB
    if free_gb < critical_free_gb:
        level = DiskLevel.CRITICAL
    elif free_gb < warn_free_gb:
        level = DiskLevel.LOW
    else:
        level = DiskLevel.OK
    return DiskStatus(path=path, free_bytes=usage.free, total_bytes=usage.total, level=level)


class DiskGuard:
    """Periodic free-space check for the recorder's data root.

    Stateful only to throttle repeat logging: every change of level is logged
    immediately, and a sustained low-disk condition re-logs at
    ``repeat_interval_s``. :meth:`check` has no effect on recording and returns
    the reading so callers (``make status``) can present it.
    """

    def __init__(
        self,
        path: Path,
        warn_free_gb: float,
        critical_free_gb: float,
        repeat_interval_s: float = REPEAT_INTERVAL_S,
    ) -> None:
        self._path = path
        self._warn_free_gb = warn_free_gb
        self._critical_free_gb = critical_free_gb
        self._repeat_interval_s = repeat_interval_s
        self._last_level: DiskLevel | None = None
        self._last_logged_s: float | None = None
        self._log = structlog.get_logger("recorder")

    def check(self, now_s: float) -> DiskStatus:
        """Read free space and log if warranted. Recording is never affected."""
        status = read_disk(self._path, self._warn_free_gb, self._critical_free_gb)
        if self._should_log(status.level, now_s):
            self._emit(status)
            self._last_logged_s = now_s
        self._last_level = status.level
        return status

    def _should_log(self, level: DiskLevel, now_s: float) -> bool:
        if level != self._last_level:
            # Includes recovery to OK, which is worth exactly one line.
            return True
        if level is DiskLevel.OK:
            return False
        return self._last_logged_s is None or now_s - self._last_logged_s >= self._repeat_interval_s

    def _emit(self, status: DiskStatus) -> None:
        fields = {
            "path": str(status.path),
            "free_gb": round(status.free_gb, 1),
            "total_gb": round(status.total_gb, 1),
            "warn_below_gb": self._warn_free_gb,
            "critical_below_gb": self._critical_free_gb,
        }
        if status.level is DiskLevel.CRITICAL:
            self._log.error(
                "disk_space_critical",
                action="recording continues; free space now or capture will be truncated",
                **fields,
            )
        elif status.level is DiskLevel.LOW:
            self._log.warning(
                "disk_space_low",
                action="recording continues; plan to free space or move completed days",
                **fields,
            )
        else:
            self._log.info("disk_space_recovered", **fields)
