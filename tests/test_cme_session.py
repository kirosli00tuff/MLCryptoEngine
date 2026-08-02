"""CME scheduled closures: expected absence must not be scored as missing data."""

from __future__ import annotations

from datetime import UTC, datetime

from data.databento.session import closed_windows_ns, is_closed, open_ns

NS_PER_S = 1_000_000_000
NS_PER_HOUR = 3600 * NS_PER_S


def _ns(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp()) * NS_PER_S


def test_weekday_has_exactly_one_hour_maintenance_halt() -> None:
    # Thursday 2026-07-30: one 16:00-17:00 CT halt = 21:00-22:00 UTC in CDT.
    windows = closed_windows_ns("2026-07-30")

    assert len(windows) == 1
    start, end = windows[0]
    assert end - start == NS_PER_HOUR
    assert datetime.fromtimestamp(start / 1e9, tz=UTC).hour == 21
    assert open_ns("2026-07-30") == 23 * NS_PER_HOUR


def test_friday_close_runs_into_the_weekend_and_saturday_is_shut() -> None:
    # Friday 2026-07-31: open until 16:00 CT (21:00 UTC), then shut.
    friday = closed_windows_ns("2026-07-31")
    assert friday, "the Friday close must appear"
    start, end = friday[-1]
    assert datetime.fromtimestamp(start / 1e9, tz=UTC).hour == 21
    # The window is clipped to the day, so it runs to midnight UTC.
    assert end == _ns("2026-08-01T00:00:00")
    assert open_ns("2026-07-31") == 21 * NS_PER_HOUR

    # Saturday is closed end to end: zero scheduled-open time.
    assert open_ns("2026-08-01") == 0
    assert is_closed(_ns("2026-08-01T12:00:00"), "2026-08-01")


def test_sunday_reopens_at_17_00_central() -> None:
    # Shut until 17:00 CT = 22:00 UTC, so 2 h of the UTC day are open.
    assert open_ns("2026-08-02") == 2 * NS_PER_HOUR
    assert is_closed(_ns("2026-08-02T12:00:00"), "2026-08-02")
    assert not is_closed(_ns("2026-08-02T23:00:00"), "2026-08-02")


def test_halt_membership_is_half_open() -> None:
    date = "2026-07-30"
    assert is_closed(_ns("2026-07-30T21:00:00"), date), "halt start is closed"
    assert is_closed(_ns("2026-07-30T21:59:59"), date)
    assert not is_closed(_ns("2026-07-30T22:00:00"), date), "reopen instant is open"
    assert not is_closed(_ns("2026-07-30T20:59:59"), date)


def test_dst_is_handled_rather_than_a_fixed_offset() -> None:
    """In CST the 16:00 CT halt is 22:00 UTC, not 21:00 — a hardcoded offset
    would silently shift the halt by an hour for half the year."""
    winter = closed_windows_ns("2026-01-15")
    assert datetime.fromtimestamp(winter[0][0] / 1e9, tz=UTC).hour == 22
    summer = closed_windows_ns("2026-07-30")
    assert datetime.fromtimestamp(summer[0][0] / 1e9, tz=UTC).hour == 21
    # Either way a weekday still has exactly 23 open hours.
    assert open_ns("2026-01-15") == 23 * NS_PER_HOUR
