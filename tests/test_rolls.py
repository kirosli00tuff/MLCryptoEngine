"""Roll boundaries: derived from symbology, excluded through the invalidity path.

Built from the real MBT rolls resolved for 2026-02-01..2026-08-02, including
the 2026-06-27 splice (42012278 -> 42101132) that sits between the two MBT
days already on disk.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from data.config import AppConfig, load_config
from data.databento.rolls import RollBoundary, read_rolls, roll_windows_ns, write_rolls
from data.recorder.gaps import merge_windows

NS_PER_S = 1_000_000_000
NS_PER_MIN = 60 * NS_PER_S
LOOKBACK_NS = 60 * NS_PER_S  # 1 min
HORIZON_NS = 900 * NS_PER_S  # 15 min, the longest label


def _ns(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp()) * NS_PER_S


# The real MBTN6 roll: MBT.c.0 switched instrument on 2026-06-27.
JUNE_ROLL = RollBoundary(
    symbol="MBT.c.0",
    date="2026-06-27",
    ts_ns=_ns("2026-06-27T00:00:00"),
    from_instrument="42012278",
    to_instrument="42101132",
)
JULY_ROLL = RollBoundary(
    symbol="MBT.c.0",
    date="2026-08-01",
    ts_ns=_ns("2026-08-01T00:00:00"),
    from_instrument="42101132",
    to_instrument="42106678",
)


def test_exclusion_covers_the_samples_whose_labels_span_the_real_roll() -> None:
    """A sample at t is unsafe iff [t-lookback, t+horizon] contains the roll,
    i.e. t in [R-horizon, R+lookback) — backward by the LABEL horizon, not
    the lookback. This is the orientation that is easy to get backwards."""
    (window,) = roll_windows_ns([JUNE_ROLL], LOOKBACK_NS, HORIZON_NS)
    lo, hi = window

    assert lo == JUNE_ROLL.ts_ns - HORIZON_NS, "must reach back one full label horizon"
    assert hi == JUNE_ROLL.ts_ns + LOOKBACK_NS, "and forward one feature lookback"
    assert hi - lo == HORIZON_NS + LOOKBACK_NS

    # A sample 10 min before the roll: its 15 min label crosses the splice.
    assert lo <= JUNE_ROLL.ts_ns - 10 * NS_PER_MIN < hi
    # A sample 30 s after: its 1 min lookback reaches back across the splice.
    assert lo <= JUNE_ROLL.ts_ns + 30 * NS_PER_S < hi
    # A sample 20 min before is safe: its label resolves before the roll.
    assert not (lo <= JUNE_ROLL.ts_ns - 20 * NS_PER_MIN < hi)
    # A sample 5 min after is safe: nothing it reads predates the roll.
    assert not (lo <= JUNE_ROLL.ts_ns + 5 * NS_PER_MIN < hi)


def test_exclusion_scales_with_configured_horizons_not_a_constant() -> None:
    narrow = roll_windows_ns([JUNE_ROLL], LOOKBACK_NS, 30 * NS_PER_S)[0]
    wide = roll_windows_ns([JUNE_ROLL], LOOKBACK_NS, HORIZON_NS)[0]
    assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])
    with pytest.raises(ValueError):
        roll_windows_ns([JUNE_ROLL], -1, HORIZON_NS)


def test_overlapping_roll_windows_are_unioned_not_summed() -> None:
    """Fourth instance of the interval rule (CLAUDE.md): two rolls closer
    together than the exclusion width must merge, not double-count."""
    close = RollBoundary(
        symbol="MBT.c.0",
        date="2026-06-27",
        ts_ns=JUNE_ROLL.ts_ns + 5 * NS_PER_MIN,  # 5 min after: windows overlap
        from_instrument="x",
        to_instrument="y",
    )
    windows = roll_windows_ns([JUNE_ROLL, close], LOOKBACK_NS, HORIZON_NS)

    assert len(windows) == 1, "overlapping roll windows must merge into one"
    total = sum(hi - lo for lo, hi in windows)
    naive = 2 * (HORIZON_NS + LOOKBACK_NS)
    assert total < naive, "summing without union would over-report excluded time"
    assert total == (close.ts_ns + LOOKBACK_NS) - (JUNE_ROLL.ts_ns - HORIZON_NS)

    # Far-apart rolls stay separate.
    assert len(roll_windows_ns([JUNE_ROLL, JULY_ROLL], LOOKBACK_NS, HORIZON_NS)) == 2


def test_roll_windows_union_cleanly_with_gap_and_closure_windows() -> None:
    """Roll exclusion joins the existing invalidity path, so its windows must
    compose with the others through the same merge helper."""
    rolls = roll_windows_ns([JUNE_ROLL], LOOKBACK_NS, HORIZON_NS)
    halt = (JUNE_ROLL.ts_ns - 20 * NS_PER_MIN, JUNE_ROLL.ts_ns - 5 * NS_PER_MIN)
    combined = merge_windows([*rolls, halt])

    assert len(combined) == 1, "overlapping exclusions collapse to one window"
    total = sum(hi - lo for lo, hi in combined)
    assert total < (rolls[0][1] - rolls[0][0]) + (halt[1] - halt[0])


def test_boundaries_round_trip_to_disk(tmp_path: Path) -> None:
    cfg = AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=load_config().venues)
    assert read_rolls(cfg, "MBT.c.0") == []

    write_rolls(cfg, "MBT.c.0", [JULY_ROLL, JUNE_ROLL])
    stored = read_rolls(cfg, "MBT.c.0")

    assert [b.date for b in stored] == ["2026-06-27", "2026-08-01"], "sorted by time"
    assert stored[0].from_instrument == "42012278"
    assert stored[0].to_instrument == "42101132"
    assert stored[0].ts_ns == _ns("2026-06-27T00:00:00")


def test_stored_mbt_rolls_are_monthly_across_the_backfill_range() -> None:
    """The resolved boundaries for the purchased range, read from disk."""
    stored = read_rolls(load_config(), "MBT.c.0")
    if not stored:
        pytest.skip("roll boundaries not yet resolved on this machine")

    assert "2026-06-27" in [b.date for b in stored], "the MBTN6 roll between the stored days"
    for earlier, later in pairwise(stored):
        days = (later.ts_ns - earlier.ts_ns) / (86_400 * NS_PER_S)
        assert 20 <= days <= 40, f"{earlier.date} -> {later.date} is {days:.0f} days"
        assert earlier.to_instrument == later.from_instrument, "contiguous splice chain"
