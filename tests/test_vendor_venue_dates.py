"""The vendor venue's dates come from ingested partitions, not raw captures.

Stage C.8 lost an overnight cycle to a silent version of this: the lookup
walked one directory too far, landed on the venue directory (whose children
are ``symbol=``, not ``date=``), and returned an empty set. That was reported
upstream as "no recorded data for ..." while 6.9 GB of ingested events sat on
disk — success-shaped output for a total failure. These tests pin the shape of
the answer, not just its emptiness.
"""

from __future__ import annotations

from pathlib import Path

from data.config import AppConfig, load_config
from data.store import BookDayWriter
from research.__main__ import _dates_available

VENUE, SYMBOL = "cme", "MBT"
DATES = ("2026-04-01", "2026-04-02", "2026-04-06")


def _write_day(processed_dir: Path, date: str, symbol: str = SYMBOL) -> None:
    writer = BookDayWriter(processed_dir, VENUE, symbol, date)
    writer.append(
        [
            {
                "venue": VENUE,
                "symbol": symbol,
                "ts_ns": 1_780_000_000_000_000_000,
                "exchange_ns": 1_779_999_999_999_000_000,
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
                "seq": 1,
                "bid_n": 1,
                "ask_n": 1,
            }
        ]
    )
    writer.close()


def _cfg(tmp_path: Path) -> AppConfig:
    # processed_dir is a property over data_root, so overriding it directly on
    # the model silently does nothing and the test reads the real dataset.
    return load_config().model_copy(update={"data_root": tmp_path})


def _processed(tmp_path: Path) -> Path:
    return tmp_path / "processed"


def test_ingested_days_are_found_for_the_vendor_venue(tmp_path: Path) -> None:
    # Arrange
    for date in DATES:
        _write_day(_processed(tmp_path), date)

    # Act
    found = _dates_available(_cfg(tmp_path), VENUE, SYMBOL)

    # Assert: the exact dates, not merely "non-empty" — the bug this replaces
    # returned a plausible-looking empty list.
    assert found == sorted(DATES)


def test_symbols_do_not_leak_into_the_date_set(tmp_path: Path) -> None:
    # Arrange: two symbols under the venue. Walking up to the venue directory
    # sees `symbol=MBT` / `symbol=MES` and, finding no `date=` prefix, returns
    # nothing at all — the exact failure that cost Stage C.8 a full cycle.
    _write_day(_processed(tmp_path), "2026-04-01", symbol="MBT")
    _write_day(_processed(tmp_path), "2026-04-02", symbol="MES")

    # Act
    mbt = _dates_available(_cfg(tmp_path), VENUE, "MBT")
    mes = _dates_available(_cfg(tmp_path), VENUE, "MES")

    # Assert
    assert mbt == ["2026-04-01"], "MBT must not see MES's days"
    assert mes == ["2026-04-02"], "MES must not see MBT's days"
    assert not any(d.startswith("symbol=") for d in mbt + mes)


def test_venue_with_nothing_ingested_returns_empty(tmp_path: Path) -> None:
    # An absent venue is genuinely empty; the point of the tests above is that
    # a POPULATED venue is never reported this way.
    assert _dates_available(_cfg(tmp_path), VENUE, SYMBOL) == []
