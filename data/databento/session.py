"""CME session windows: absence of data during a halt is not missing data.

GLBX runs nearly around the clock but not continuously. Each weekday has a
60-minute maintenance halt (16:00-17:00 US/Central), and the week closes
Friday 16:00 CT through Sunday 17:00 CT. Quiet time inside those windows is
the exchange being shut, not a gap in capture — scoring it as missing
coverage would understate every CME day by ~4% and would flag a scheduled
halt as an anomaly.

This mirrors what the recorder path gets from ``gaps.jsonl`` and session
markers (ADR-007): coverage is only ever measured against time the venue was
actually open. The difference is that a vendor feed has no reconnect log, so
expected absence has to come from the exchange calendar instead.

Times convert from US/Central via ``zoneinfo`` rather than a fixed UTC
offset — a hardcoded offset silently breaks twice a year.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from data.recorder.gaps import merge_windows

CME_TZ = ZoneInfo("America/Chicago")
NS_PER_S = 1_000_000_000

# Daily maintenance halt, US/Central.
HALT_START = time(16, 0)
HALT_END = time(17, 0)
FRIDAY, SATURDAY = 4, 5


def _to_ns(moment: datetime) -> int:
    return int(moment.astimezone(UTC).timestamp()) * NS_PER_S


def closed_windows_ns(date: str) -> list[tuple[int, int]]:
    """Half-open ``[start, end)`` windows when GLBX is scheduled shut.

    Considers the local days either side of the UTC date so a halt straddling
    midnight UTC is caught, then clips to the requested day.
    """
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    day_start_ns, day_end_ns = _to_ns(day), _to_ns(day + timedelta(days=1))

    windows: list[tuple[int, int]] = []
    for offset in (-2, -1, 0, 1):
        local_day = (day + timedelta(days=offset)).astimezone(CME_TZ).date()
        weekday = local_day.weekday()
        if weekday == SATURDAY:
            continue  # inside the Friday-to-Sunday window
        halt_start = datetime.combine(local_day, HALT_START, tzinfo=CME_TZ)
        if weekday == FRIDAY:
            reopen = datetime.combine(local_day + timedelta(days=2), HALT_END, tzinfo=CME_TZ)
            windows.append((_to_ns(halt_start), _to_ns(reopen)))
        else:
            halt_end = datetime.combine(local_day, HALT_END, tzinfo=CME_TZ)
            windows.append((_to_ns(halt_start), _to_ns(halt_end)))

    clipped = [
        (max(start, day_start_ns), min(end, day_end_ns))
        for start, end in windows
        if min(end, day_end_ns) > max(start, day_start_ns)
    ]
    # Union, never a bare sort: the Friday-to-Sunday close overlaps Sunday's
    # own daily halt, and summing both would count that hour twice — the same
    # double-counting the Stage 1.5 gap accounting had to fix.
    return merge_windows(clipped)


def open_ns(date: str) -> int:
    """Nanoseconds of the UTC day the exchange was scheduled open."""
    day_ns = 86_400 * NS_PER_S
    return day_ns - sum(end - start for start, end in closed_windows_ns(date))


def is_closed(ts_ns: int, date: str) -> bool:
    return any(start <= ts_ns < end for start, end in closed_windows_ns(date))
