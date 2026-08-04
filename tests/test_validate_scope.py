"""Run planning: what gets validated, what gets skipped, and what must be loud.

Adding the vendor-backfill venue `cme` to config/venues.yaml made
`python -m data.validate --date <today>` raise before validating anything: the
CLI treated every configured venue as replayable, so the one venue that can
never have raw capture aborted the run and took the three healthy venues with
it. These tests pin the three outcomes apart — replay, skip-with-a-reason, and
fail-loudly — because collapsing any two of them is how a venue either crashes
a run or drops out of validation unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.config import AppConfig, VenueConfig, load_config
from data.recorder.writer import RawFileWriter
from data.validate.replay import VenueConfigurationError, validate_venue_day
from data.validate.report_writer import append_report
from data.validate.scope import VENDOR_SCHEMA, plan_run, vendor_dates, vendor_symbols_on

NS_PER_S = 1_000_000_000
DATE = "2026-07-30"
BASE_NS = 1_785_412_800 * NS_PER_S  # 2026-07-30T12:00:00Z
VENDOR_DATE = "2026-07-31"


def _cfg(tmp_path: Path, venues: dict[str, VenueConfig] | None = None) -> AppConfig:
    return AppConfig(
        data_root=tmp_path,
        logs_dir=tmp_path / "logs",
        venues=venues if venues is not None else load_config().venues,
    )


def _record_a_day(tmp_path: Path, venue: str) -> None:
    writer = RawFileWriter(tmp_path / "raw", venue)
    try:
        writer.write(BASE_NS, '{"channel":"book"}')
    finally:
        writer.close()


def _store_vendor_file(tmp_path: Path, symbol_on_disk: str, schema: str = VENDOR_SCHEMA) -> Path:
    day_dir = tmp_path / "vendor" / "databento" / "GLBX.MDP3" / f"date={VENDOR_DATE}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{symbol_on_disk}.{schema}.dbn.zst"
    path.write_bytes(b"")  # planning reads the name, never the contents
    return path


def test_a_venue_with_no_data_is_skipped_while_the_others_still_replay(tmp_path: Path) -> None:
    """The defect in one sentence: one empty venue must not cancel the rest."""
    # Arrange: kraken recorded this day, coinbase recorded nothing at all.
    _record_a_day(tmp_path, "kraken")
    cfg = _cfg(tmp_path)

    # Act
    plan = plan_run(cfg, ["kraken", "coinbase"], [DATE])

    # Assert
    assert [(d.venue, d.date) for d in plan.recorder_days] == [("kraken", DATE)]
    (skip,) = plan.skipped
    assert skip.venue == "coinbase"
    assert skip.kind == "recorder"
    assert DATE in skip.reason
    assert not plan.is_empty


def test_a_recorder_venue_missing_only_the_requested_date_says_so(tmp_path: Path) -> None:
    # Arrange: data exists, but not on the date asked for.
    _record_a_day(tmp_path, "kraken")
    cfg = _cfg(tmp_path)

    # Act
    plan = plan_run(cfg, ["kraken"], ["2026-07-29"])

    # Assert: the reason distinguishes "not this date" from "nothing ever".
    assert plan.recorder_days == []
    (skip,) = plan.skipped
    assert "2026-07-29" in skip.reason
    assert "1 other recorded date" in skip.reason


def test_the_vendor_venue_is_skipped_in_a_default_sweep_never_raised_on(tmp_path: Path) -> None:
    # Arrange: every configured venue, as `make validate` runs it.
    _record_a_day(tmp_path, "kraken")
    cfg = _cfg(tmp_path)

    # Act
    plan = plan_run(cfg, None, [DATE])

    # Assert: cme is reported as a vendor venue, and kraken still replays.
    assert [d.venue for d in plan.recorder_days] == ["kraken"]
    cme = next(s for s in plan.skipped if s.venue == "cme")
    assert cme.kind == "vendor"
    assert "not captured live" in cme.reason
    assert plan.vendor_days == []


def test_naming_the_vendor_venue_plans_its_stored_days(tmp_path: Path) -> None:
    # Arrange: two contracts stored for one date, plus a trades file that is
    # not the book and must not be planned as one.
    _store_vendor_file(tmp_path, "MBT_c_0")
    _store_vendor_file(tmp_path, "MES_c_0")
    _store_vendor_file(tmp_path, "MBT_c_0", schema="trades")
    cfg = _cfg(tmp_path)

    # Act
    plan = plan_run(cfg, ["cme"], [VENDOR_DATE])

    # Assert: underscores on disk map back to the continuous symbology.
    assert [(d.symbol, d.date, d.schema) for d in plan.vendor_days] == [
        ("MBT.c.0", VENDOR_DATE, VENDOR_SCHEMA),
        ("MES.c.0", VENDOR_DATE, VENDOR_SCHEMA),
    ]
    assert plan.skipped == []
    assert vendor_dates(cfg) == [VENDOR_DATE]
    assert vendor_symbols_on(cfg, VENDOR_DATE) == ["MBT.c.0", "MES.c.0"]


def test_the_vendor_venue_with_no_stored_file_is_skipped_not_raised_on(tmp_path: Path) -> None:
    # Arrange: asked for by name, but nothing on disk for that date.
    cfg = _cfg(tmp_path)

    # Act
    plan = plan_run(cfg, ["cme"], [VENDOR_DATE])

    # Assert
    assert plan.is_empty
    (skip,) = plan.skipped
    assert skip.kind == "vendor"
    assert VENDOR_DATE in skip.reason
    assert "range=" in skip.reason, "must point at the range validator, not dead-end"


def test_a_recorder_venue_with_no_parser_is_a_loud_configuration_error(tmp_path: Path) -> None:
    """The one case that must still raise: a venue we believe we are capturing
    live but cannot reconstruct. Skipping it quietly would let a venue fall out
    of validation with nothing in the output to show it."""
    # Arrange: cme mislabelled as recorder-backed — no parser exists for it.
    venues = dict(load_config().venues)
    venues["cme"] = venues["cme"].model_copy(update={"kind": "recorder"})
    cfg = _cfg(tmp_path, venues)

    # Act / Assert
    with pytest.raises(VenueConfigurationError, match="nothing can replay it"):
        plan_run(cfg, None, [DATE])


def test_an_unknown_venue_key_is_a_configuration_error(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)

    with pytest.raises(VenueConfigurationError, match="unknown venue 'nosuch'"):
        plan_run(cfg, ["nosuch"], [DATE])


def test_the_vendor_venue_is_refused_by_the_raw_capture_replay_path(tmp_path: Path) -> None:
    """Defence in depth: even called directly, the replay path must not pretend
    it can score a venue whose data never lands in data/raw/."""
    cfg = _cfg(tmp_path)

    with pytest.raises(VenueConfigurationError, match="kind='vendor'"):
        validate_venue_day(cfg, "cme", DATE)


def test_skipped_venues_reach_report_md_not_just_the_terminal(tmp_path: Path) -> None:
    """A section listing two venues where three were expected must say what
    happened to the third. Printing it to a terminal nobody kept is not a
    record — the permanent report has to show that a venue went unscored."""
    # Arrange
    _record_a_day(tmp_path, "kraken")
    cfg = _cfg(tmp_path)
    plan = plan_run(cfg, None, [DATE])
    report_path = tmp_path / "report.md"

    # Act
    append_report(report_path, [], [], plan.skipped)
    written = report_path.read_text(encoding="utf-8")

    # Assert: every skipped venue named, with its kind and its reason.
    assert "Venues skipped" in written
    for skip in plan.skipped:
        assert f"**{skip.venue}**" in written
        assert f"`{skip.kind}`" in written
        assert skip.reason in written
    assert "cme" in written and "vendor" in written
