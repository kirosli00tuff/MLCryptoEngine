"""CME exclusion windows: one union feeding the existing invalidity path.

The recorder venues derive invalid time from feed gaps and recorder downtime
(``research.stream.reader.gap_windows``). CME has no recorder, so its invalid
time comes from four sources instead, and this module unions them into the
single window list the sampler already understands. Nothing here is a new
mechanism — it is the same ``[start, end)`` list, produced differently.

The four classes, and why each one invalidates a sample:

1. **Scheduled closures** — the daily maintenance halt and the weekend. A
   sample whose 900 s label horizon reaches across the Friday close resolves
   against a mid from Sunday evening, turning a 15-minute return into a
   two-day one.
2. **No-match windows** — the halt plus the reopen auction grace, where order
   entry continues while matching is suspended so the book legitimately
   crosses (ADR-019).
3. **Roll boundaries** — the continuous series splices instruments, and a
   lookback or horizon spanning the splice mixes two contracts (ADR-020).
4. **Observed silences** — stretches inside scheduled-open time where no book
   update arrives at all. Stage C.7 found ~6.0 h of these on each MBT expiry
   session: the contract settles at 16:00 London while CME stays open until
   16:00 CT, so the book sits dead for the remainder. The labeler resolves
   such a deadline against the last mid *before* the silence, which is not
   lookahead but is a stale label — a "900 s return" measured over 100 s of
   live market and then nothing. Those samples must be invalid.

Class 4 is why this module reads the data rather than only the calendar: a
silence is an observed property of the feed, not a scheduled one, and Stage
C.7 showed the roll exclusion centred on the splice covers none of it.

Every list is unioned through :func:`merge_windows` before it is returned or
summed — the CLAUDE.md interval rule, whose whole point is that overlapping
windows (a Friday close overlapping that day's own halt, a roll window
overlapping a silence) must never be added twice.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from data.config import AppConfig
from data.databento.rolls import RollBoundary, roll_windows_ns
from data.databento.session import closed_windows_ns, no_match_windows_ns
from data.recorder.gaps import merge_windows
from data.store import book_partition_dir
from data.store.parquet_writer import PART_NAME

NS_PER_S = 1_000_000_000
NS_PER_MS = 1_000_000
# A stretch with no book update longer than this, inside scheduled-open time,
# is treated as missing data rather than as a quiet market. Matches the
# validator's QUIET_ANOMALY_MS so a day the validator calls silent and a
# sample the pipeline calls invalid never disagree.
SILENCE_THRESHOLD_NS = 60 * NS_PER_S


def observed_silences_ns(
    processed_dir: Path,
    venue: str,
    symbol: str,
    date: str,
    threshold_ns: int = SILENCE_THRESHOLD_NS,
) -> list[tuple[int, int]]:
    """Stretches with no book update longer than ``threshold_ns``.

    Reads only the timestamp column, so a day of several million rows costs
    one columnar scan and holds one array rather than the rows themselves.
    """
    path = book_partition_dir(processed_dir, venue, symbol, date) / PART_NAME
    if not path.is_file():
        return []
    table = pq.read_table(path, columns=["ts_ns"])
    stamps = table.column("ts_ns").to_numpy()
    if stamps.size < 2:
        return []
    deltas = stamps[1:] - stamps[:-1]
    (idx,) = (deltas > threshold_ns).nonzero()
    return merge_windows((int(stamps[i]), int(stamps[i + 1])) for i in idx)


def exclusion_windows_ns(
    cfg: AppConfig,
    symbol: str,
    date: str,
    rolls: list[RollBoundary],
    lookback_ns: int,
    horizon_ns: int,
    venue: str = "cme",
) -> list[tuple[int, int]]:
    """Union of every window that makes a CME sample invalid on ``date``.

    ``lookback_ns``/``horizon_ns`` size the roll exclusion and are passed
    through from the pipeline's own feature lookback and longest label
    horizon, so extending either widens the exclusion automatically rather
    than leaving a constant behind to rot.
    """
    windows: list[tuple[int, int]] = []
    windows.extend(closed_windows_ns(date))
    windows.extend(no_match_windows_ns(date))
    windows.extend(roll_windows_ns(rolls, lookback_ns, horizon_ns))
    windows.extend(observed_silences_ns(cfg.processed_dir, venue, symbol, date))
    return merge_windows(windows)
