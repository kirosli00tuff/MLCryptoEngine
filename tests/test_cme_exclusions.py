"""CME exclusion windows: observed silences, and the union that must not sum.

Stage C.7 found ~6.0 h of dead book on each MBT expiry session — the contract
settles at 16:00 London while CME stays open to 16:00 CT. Those hours sit
inside scheduled-open time, so no calendar catches them; only the data does.
"""

from __future__ import annotations

from pathlib import Path

from data.databento.exclusions import SILENCE_THRESHOLD_NS, observed_silences_ns
from data.databento.rolls import RollBoundary, roll_windows_ns
from data.recorder.gaps import merge_windows
from data.store import BookDayWriter

DATE = "2026-05-29"  # an MBT expiry Friday
NS_PER_S = 1_000_000_000
BASE = 1_780_000_000 * NS_PER_S


def _write_book(tmp_path: Path, stamps: list[int]) -> None:
    writer = BookDayWriter(tmp_path, "cme", "MBT", DATE)
    writer.append(
        [
            {
                "venue": "cme",
                "symbol": "MBT",
                "ts_ns": ts,
                "exchange_ns": ts - 1_000,
                "source": "databento",
                "kind": "event",
                "valid": True,
                "crossed": False,
                "locked": False,
                "best_bid": 65_000.0,
                "bid_qty": 1.0,
                "best_ask": 65_005.0,
                "ask_qty": 1.0,
                "mid": 65_002.5,
                "microprice": 65_002.5,
                "bid_prices": [],
                "bid_qtys": [],
                "ask_prices": [],
                "ask_qtys": [],
                "seq": i,
                "bid_n": 1,
                "ask_n": 1,
            }
            for i, ts in enumerate(stamps)
        ]
    )
    writer.close()


def test_a_six_hour_dead_book_is_found_as_one_silence(tmp_path: Path) -> None:
    # Arrange: active, then the post-settlement silence, then one last print.
    dead_start = BASE + 100 * NS_PER_S
    dead_end = dead_start + 6 * 3600 * NS_PER_S
    _write_book(tmp_path, [BASE, BASE + 50 * NS_PER_S, dead_start, dead_end])

    # Act
    silences = observed_silences_ns(tmp_path, "cme", "MBT", DATE)

    # Assert
    assert silences == [(dead_start, dead_end)]
    assert (dead_end - dead_start) / 3600 / NS_PER_S == 6.0


def test_a_quiet_market_below_the_threshold_is_not_a_silence(tmp_path: Path) -> None:
    # Arrange: 59 s between prints — thin, but a true observation of a quiet
    # market rather than missing data.
    quiet = SILENCE_THRESHOLD_NS - NS_PER_S
    _write_book(tmp_path, [BASE, BASE + quiet, BASE + 2 * quiet])

    # Act / Assert
    assert observed_silences_ns(tmp_path, "cme", "MBT", DATE) == []


def test_missing_partition_yields_no_silences(tmp_path: Path) -> None:
    # A day never ingested has no observations, which is not the same as a
    # day observed to be silent — it must not manufacture a window.
    assert observed_silences_ns(tmp_path, "cme", "MBT", "2026-01-01") == []


def test_overlapping_silence_and_roll_windows_are_unioned_not_summed(tmp_path: Path) -> None:
    # Arrange: the fifth instance of the CLAUDE.md interval rule. A roll
    # splice landing inside an expiry-day silence produces two windows that
    # overlap, and summing them double-counts the overlap.
    dead_start = BASE + 100 * NS_PER_S
    dead_end = dead_start + 6 * 3600 * NS_PER_S
    # The 50 s print keeps the run-up under the silence threshold, so the
    # dead window is the only silence and the overlap under test is the one
    # between it and the roll.
    _write_book(tmp_path, [BASE, BASE + 50 * NS_PER_S, dead_start, dead_end])
    silences = observed_silences_ns(tmp_path, "cme", "MBT", DATE)

    roll_at = dead_start + 3600 * NS_PER_S  # one hour into the silence
    rolls = roll_windows_ns(
        [
            RollBoundary(
                symbol="MBT.c.0",
                date=DATE,
                ts_ns=roll_at,
                from_instrument="A",
                to_instrument="B",
            )
        ],
        lookback_ns=60 * NS_PER_S,
        horizon_ns=900 * NS_PER_S,
    )

    # Act
    unioned = merge_windows(silences + rolls)
    summed = sum(end - start for start, end in silences + rolls)
    covered = sum(end - start for start, end in unioned)

    # Assert
    assert len(unioned) == 1, "the roll window sits wholly inside the silence"
    assert covered == dead_end - dead_start
    assert summed > covered, "summing without a union double-counts the overlap"
