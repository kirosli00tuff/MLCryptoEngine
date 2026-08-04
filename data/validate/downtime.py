"""Derive recorder-downtime gaps from session lifecycle markers.

Between a session-end marker and the next session-start lies a period with no
recorder — a ``downtime`` gap. A start following a start with no end between
them means the previous process died without shutting down cleanly (crash,
OOM kill, power loss): the hole is measured from the last observed activity
(the final raw message on disk) up to the new start and marked ``unclean`` so
it can never pass as a planned stop. Derived gaps are ordinary
:class:`GapRecord` values, so span clamping, unioning, and anomaly
explanation treat them exactly like feed gaps while reports keep the causes
separate.

**File order in sessions.jsonl is unreliable by design, not by accident.** Two
processes append to one file during every restart: the incoming recorder writes
its ``start`` as soon as it is up, and the outgoing one writes its ``end`` while
shutting down. Whichever wins the race lands first. A real instance on disk::

    {"venue":"kraken","event":"start","ts_ns":1785569177909450362}
    {"venue":"kraken","event":"end",  "ts_ns":1785569177581971000}

The ``end`` is 327 ms *earlier* than the ``start`` above it. The timestamps are
correct; only the line order is wrong. Reading them sequentially pairs the wrong
markers — that sequence read in file order reports a 602 ms **unclean
termination**, mislabelling a graceful systemd restart as a crash, and loses the
327 ms clean downtime gap entirely.

So markers are ordered by ``ts_ns`` before pairing, never by position, with
``end`` breaking ties ahead of ``start`` at an identical timestamp (a restart
ends before it begins; the reverse reading would invent an unclean termination
out of a zero-length stop). Adding a marker source, or a reader that streams
rather than loads, does not change this: order by the clock, always.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from data.recorder.gaps import GapRecord
from data.recorder.reader import available_dates, hour_files, iter_raw_records
from data.recorder.sessions import SessionMarker

CLEAN_REASON = "recorder not running (clean shutdown to next start)"
UNCLEAN_REASON = (
    "recorder terminated uncleanly (no session-end marker); "
    "downtime measured from last observed activity"
)

LastActivityFn = Callable[[int], "int | None"]


def _order(marker: SessionMarker) -> tuple[int, bool]:
    """Sort key: the clock first, then ``end`` ahead of ``start`` on a tie.

    ``False`` sorts before ``True``, so ``event == "start"`` puts ends first.
    A restart whose two markers share a timestamp then reads as a zero-length
    stop instead of an unclean termination.
    """
    return marker.ts_ns, marker.event == "start"


def last_activity_ns(raw_dir: Path, venue: str, before_ns: int) -> int | None:
    """Receive timestamp of the venue's last raw message strictly before ``before_ns``.

    Scans dates and hour files newest-first and stops at the first file
    containing any qualifying record, so the cost is bounded by a handful of
    hour files rather than the whole archive.
    """
    for date in reversed(available_dates(raw_dir, venue)):
        for path in reversed(hour_files(raw_dir, venue, date)):
            last: int | None = None
            for recv_ns, _raw in iter_raw_records(path):
                if recv_ns < before_ns and (last is None or recv_ns > last):
                    last = recv_ns
            if last is not None:
                return last
    return None


def _gap(venue: str, start_ns: int, end_ns: int, kind: str, reason: str) -> GapRecord:
    return GapRecord(
        venue=venue,
        disconnect_ns=start_ns,
        reconnect_ns=end_ns,
        duration_ms=(end_ns - start_ns) // 1_000_000,
        reason=reason,
        kind=kind,  # type: ignore[arg-type]
    )


def derive_downtime_gaps(
    markers: list[SessionMarker],
    last_activity: LastActivityFn,
) -> list[GapRecord]:
    """Downtime gaps implied by the marker sequence, oldest first.

    Markers are ordered by ``ts_ns`` (see the module docstring — file order is
    a race between two processes and means nothing), then paired:

    end → start: one clean ``downtime`` gap spanning the interval.
    start → start with no end between: the previous session terminated
    uncleanly; the gap runs from its last observed activity (never earlier
    than that session's own start) to the new start, kind ``unclean``.
    A trailing start with no end is a live session, not downtime.

    Zero-length intervals produce no gap. A *backwards* interval produces no
    gap either — it raises :class:`~data.recorder.gaps.NegativeGapError`
    through ``GapRecord``. After ordering by the clock that is structurally
    impossible, which is exactly why it is worth asserting: if it ever fires,
    the ordering or the marker file itself is corrupt, and silently dropping
    the pair (what the previous guard did) would have hidden that.
    """
    gaps: list[GapRecord] = []
    pending_end: SessionMarker | None = None
    open_start: SessionMarker | None = None
    for marker in sorted(markers, key=_order):
        if marker.event == "end":
            pending_end = marker
            open_start = None
            continue
        if pending_end is not None:
            if marker.ts_ns != pending_end.ts_ns:
                gaps.append(
                    _gap(marker.venue, pending_end.ts_ns, marker.ts_ns, "downtime", CLEAN_REASON)
                )
            pending_end = None
        elif open_start is not None:
            activity = last_activity(marker.ts_ns)
            begin = open_start.ts_ns if activity is None else max(activity, open_start.ts_ns)
            if marker.ts_ns != begin:
                gaps.append(_gap(marker.venue, begin, marker.ts_ns, "unclean", UNCLEAN_REASON))
        open_start = marker
    return gaps
