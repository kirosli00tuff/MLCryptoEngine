"""Integrity scoring: a check that cannot run must never look like a clean pass.

Kraken WS v2 carries no sequence number and Coinbase Advanced Trade carries no
book checksum, so on each venue exactly one of the two integrity checks is
structurally unavailable. Before Stage 1.6 both unavailable checks reported
``0 failures``, which is indistinguishable in a report from a check that ran
and found nothing. These tests pin the corrected behaviour: unavailable is
``None``/"n/a", and a *declared* mechanism that performed zero comparisons is a
FAIL rather than a silent pass.
"""

from __future__ import annotations

from pathlib import Path

from data.config import AppConfig, VenueConfig, load_config
from data.recorder.writer import RawFileWriter
from data.validate.integrity import CHECKSUM, SEQUENCE, IntegrityReport, uncertified_reason
from data.validate.replay import validate_venue_day
from data.validate.report_writer import render_section
from tests.conftest import FIXTURES_DIR

DATE = "2026-07-30"
# 2026-07-30T12:00:00Z, so every synthetic message lands inside DATE.
BASE_NS = 1_785_412_800 * 1_000_000_000


def _venues() -> dict[str, VenueConfig]:
    """The real shipped venue metadata — the asymmetry under test lives in it."""
    return load_config().venues


def _record(raw_dir: Path, venue: str, fixture: str) -> None:
    """Replay a fixture through the real writer into a synthetic venue-day."""
    lines = [
        line
        for line in (FIXTURES_DIR / fixture).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    writer = RawFileWriter(raw_dir, venue)
    try:
        for index, line in enumerate(lines):
            writer.write(BASE_NS + index * 1_000_000, line)
    finally:
        writer.close()


def _config(tmp_path: Path, venues: dict[str, VenueConfig]) -> AppConfig:
    return AppConfig(data_root=tmp_path, logs_dir=tmp_path / "logs", venues=venues)


# --- Kraken is scored on checksums, never credited with a sequence check -----


def test_kraken_reports_sequence_check_as_not_applicable(tmp_path: Path) -> None:
    venues = _venues()
    _record(tmp_path / "raw", "kraken", "kraken_messages.ndjson")

    report = validate_venue_day(_config(tmp_path, venues), "kraken", DATE)

    assert report.integrity.mechanism == CHECKSUM
    assert report.integrity.sequence_checks is None, "no sequence numbers on this feed"
    assert report.integrity.checksum_checks == 60
    for symbol in report.symbols:
        assert symbol.seq_gaps is None, "an unavailable check must not report 0"
        assert symbol.seq_gaps_unexplained is None
        assert symbol.checksum_failures == 0
        assert symbol.checksums_verified == 60


def test_kraken_report_says_n_a_rather_than_zero_sequence_gaps(tmp_path: Path) -> None:
    venues = _venues()
    _record(tmp_path / "raw", "kraken", "kraken_messages.ndjson")

    section = render_section([validate_venue_day(_config(tmp_path, venues), "kraken", DATE)])

    assert f"Integrity mechanism: **{CHECKSUM}**" in section
    assert "sequence numbers: n/a (this feed provides none)" in section
    assert "book checksums: 60 checked" in section
    # The symbol row carries n/a in the seq column, not "0 (0)".
    row = next(line for line in section.splitlines() if line.startswith("| BTC/USD"))
    assert "| n/a |" in row


def test_kraken_symbol_without_precisions_fails_instead_of_passing(tmp_path: Path) -> None:
    """The silent-pass hole: no ``instruments`` entry means no checksum function,
    so every update replays unverified while the scorecard shows 0 failures."""
    venues = _venues()
    kraken = venues["kraken"].model_copy(update={"instruments": {}})
    _record(tmp_path / "raw", "kraken", "kraken_messages.ndjson")

    report = validate_venue_day(_config(tmp_path, {**venues, "kraken": kraken}), "kraken", DATE)

    assert report.integrity.checksum_checks == 0
    assert not report.passed
    assert any("not evidence of integrity" in reason for reason in report.failure_reasons)


# --- Coinbase is scored on sequence numbers, never credited with checksums ---


def test_coinbase_reports_checksum_check_as_not_applicable(tmp_path: Path) -> None:
    venues = _venues()
    _record(tmp_path / "raw", "coinbase", "coinbase_messages.ndjson")

    report = validate_venue_day(_config(tmp_path, venues), "coinbase", DATE)

    assert report.integrity.mechanism == SEQUENCE
    assert report.integrity.checksum_checks is None, "this feed provides no checksums"
    assert report.integrity.sequence_checks is not None
    assert report.integrity.sequence_checks > 0
    for symbol in report.symbols:
        assert symbol.checksum_failures is None, "an unavailable check must not report 0"
        assert symbol.checksums_verified is None
        assert symbol.seq_gaps == 0


def test_crossed_book_criterion_names_the_mechanism_that_scored_it(tmp_path: Path) -> None:
    venues = _venues()
    _record(tmp_path / "raw", "coinbase", "coinbase_messages.ndjson")

    section = render_section([validate_venue_day(_config(tmp_path, venues), "coinbase", DATE)])

    assert f"Integrity mechanism: **{SEQUENCE}**" in section
    assert "book checksums: n/a (this feed provides none)" in section


# --- a venue with no mechanism at all cannot be certified --------------------


def test_venue_with_neither_mechanism_is_uncertified(tmp_path: Path) -> None:
    venues = _venues()
    blind = venues["coinbase"].model_copy(update={"sequence_numbers": False})
    _record(tmp_path / "raw", "coinbase", "coinbase_messages.ndjson")

    report = validate_venue_day(_config(tmp_path, {**venues, "coinbase": blind}), "coinbase", DATE)

    assert report.integrity.mechanism == "none available"
    assert report.integrity.sequence_checks is None
    assert not report.passed
    assert any("no integrity mechanism available" in r for r in report.failure_reasons)
    for symbol in report.symbols:
        assert symbol.seq_gaps is None
        assert symbol.checksum_failures is None


def test_declared_mechanism_with_zero_checks_is_a_failure_not_a_pass() -> None:
    sequenced = IntegrityReport(mechanism=SEQUENCE, sequence_checks=0)
    checksummed = IntegrityReport(mechanism=CHECKSUM, checksum_checks=0)
    healthy = IntegrityReport(mechanism=CHECKSUM, checksum_checks=7_703)

    assert uncertified_reason("coinbase", [SEQUENCE], sequenced)
    assert uncertified_reason("kraken", [CHECKSUM], checksummed)
    assert uncertified_reason("kraken", [], healthy), "no mechanism at all is never certifiable"
    assert uncertified_reason("kraken", [CHECKSUM], healthy) is None
