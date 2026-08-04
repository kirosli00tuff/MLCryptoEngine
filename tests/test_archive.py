"""Archive acquisition: provenance, point-in-time selection, spliced series.

The survivorship defect this package exists to prevent is invisible in its own
output — a universe screened on today's liquidity looks exactly like one that
was not, and produces better numbers. So these tests pin the selection *rule*
rather than the result, and pin the two ways a price series can be
discontinuous while looking continuous.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pytest

from data.archive import binance, manifest, series
from data.config import AppConfig, load_config

# 2021-08-01T00:00:00Z in milliseconds, the unit older Binance dumps use.
BASE_MS = 1_627_776_000_000


def _cfg(tmp_path: Path) -> AppConfig:
    loaded = load_config()
    return AppConfig(
        data_root=tmp_path,
        logs_dir=tmp_path / "logs",
        venues=loaded.venues,
        sources=loaded.sources,
    )


def _write_month(
    cfg: AppConfig,
    symbol: str,
    period: str,
    closes: list[float],
    start_ms: int = BASE_MS,
    header: bool = False,
) -> Path:
    """Write a synthetic monthly kline ZIP in Binance's exact CSV layout."""
    path = binance.month_path(cfg, symbol, "1d", period)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if header:
        writer.writerow(
            [
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "count",
                "taker_base",
                "taker_quote",
                "ignore",
            ]
        )
    for i, close in enumerate(closes):
        open_ms = start_ms + i * 86_400_000
        writer.writerow(
            [open_ms, close, close, close, close, 1.0, open_ms + 86_399_999, 1000.0, 10, 0, 0, 0]
        )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{symbol}-1d-{period}.csv", buffer.getvalue())
    return path


def test_kline_parsing_handles_both_dump_generations(tmp_path: Path) -> None:
    """Header rows and microsecond timestamps both fail silently when guessed
    wrong: a header parses as a bar of NaNs, and a microsecond open time read
    as milliseconds lands in the year 51,000."""
    # Arrange
    cfg = _cfg(tmp_path)
    _write_month(cfg, "OLDUSDT", "2021-08", [1.0, 2.0], start_ms=BASE_MS)
    _write_month(cfg, "NEWUSDT", "2021-08", [3.0, 4.0], start_ms=BASE_MS * 1_000, header=True)

    # Act
    old = binance.read_month(binance.month_path(cfg, "OLDUSDT", "1d", "2021-08"))
    new = binance.read_month(binance.month_path(cfg, "NEWUSDT", "1d", "2021-08"))

    # Assert: both land on the same instant despite different units.
    assert [b.close for b in old] == [1.0, 2.0]
    assert [b.close for b in new] == [3.0, 4.0], "the header row must not become a bar"
    assert old[0].open_ns == new[0].open_ns == BASE_MS * 1_000_000


def test_candidate_symbols_drops_pegs_and_the_non_ascii_listings() -> None:
    """Pegged pairs are cointegrated by construction — a study reporting
    USDC/USDT as its best pair has rediscovered the peg. The non-ASCII entries
    are real: five promotional directories in the live listing, one of which
    ends in USDT and also breaks urllib's ASCII request encoding."""
    listed = ["BTCUSDT", "USDCUSDT", "DAIUSDT", "ETHBTC", "币安人生USDT", "USDT", "ETHUSDT"]

    assert binance.candidate_symbols(listed) == ["BTCUSDT", "ETHUSDT"]


def test_months_between_is_inclusive_and_crosses_the_year_boundary() -> None:
    assert binance.months_between("2021-11", "2022-02") == [
        "2021-11",
        "2021-12",
        "2022-01",
        "2022-02",
    ]
    assert binance.months_between("2021-08", "2021-08") == ["2021-08"]
    with pytest.raises(ValueError, match="precedes"):
        binance.months_between("2022-01", "2021-01")


def test_a_ticker_reused_for_a_new_asset_is_excluded_not_traded(tmp_path: Path) -> None:
    """The LUNAUSDT case, reduced. Terra collapsed in May 2022 and Terra 2.0
    relaunched on the same ticker: the monthly files run unbroken, but the
    series is two different assets spliced at a 177,000x jump. Nothing
    downstream complains — a splice looks like a structural break, and a
    structural break looks like a relationship that decayed."""
    # Arrange: a collapse to near zero, then a relaunch at a normal price.
    cfg = _cfg(tmp_path)
    closes = [80.0] * 10 + [0.0001] * 5 + [8.87] * 15
    _write_month(cfg, "REUSEDUSDT", "2021-08", closes)
    _write_month(cfg, "CLEANUSDT", "2021-08", [10.0 + 0.1 * i for i in range(30)])

    # Act
    matrix = series.build_matrix(cfg, ["REUSEDUSDT", "CLEANUSDT"], "1d", ["2021-08"])

    # Assert
    assert matrix.symbols == ["CLEANUSDT"]
    assert "REUSEDUSDT" in matrix.excluded
    assert "spliced" in matrix.excluded["REUSEDUSDT"]
    assert len(matrix.discontinuities) >= 2, "both the collapse and the relaunch"


def test_an_ordinary_crash_is_not_mistaken_for_a_splice(tmp_path: Path) -> None:
    """The detector must not fire on real volatility. A 60% single-day fall is
    brutal and entirely real; a 5x move is not."""
    cfg = _cfg(tmp_path)
    _write_month(cfg, "VOLATILEUSDT", "2021-08", [100.0] * 5 + [40.0] * 25)

    matrix = series.build_matrix(cfg, ["VOLATILEUSDT"], "1d", ["2021-08"])

    assert matrix.symbols == ["VOLATILEUSDT"]
    assert matrix.discontinuities == []


def test_a_dead_asset_keeps_its_gap_instead_of_being_filled_forward(tmp_path: Path) -> None:
    """Forward-filling a delisted asset invents a flat series, and flat series
    are trivially cointegrated with each other — manufacturing exactly the
    relationships this study is trying to measure."""
    # Arrange: one symbol stops after the first month.
    cfg = _cfg(tmp_path)
    august = BASE_MS
    september = BASE_MS + 31 * 86_400_000
    _write_month(cfg, "DEADUSDT", "2021-08", [1.0 + 0.01 * i for i in range(31)], august)
    _write_month(cfg, "ALIVEUSDT", "2021-08", [5.0 + 0.01 * i for i in range(31)], august)
    _write_month(cfg, "ALIVEUSDT", "2021-09", [6.0 + 0.01 * i for i in range(30)], september)

    # Act
    matrix = series.build_matrix(cfg, ["DEADUSDT", "ALIVEUSDT"], "1d", ["2021-08", "2021-09"])

    # Assert
    assert matrix.observations("ALIVEUSDT") == 61
    assert matrix.observations("DEADUSDT") == 31, "the dead asset must not be extended"
    dates, a, b = matrix.overlap("DEADUSDT", "ALIVEUSDT")
    assert dates.size == 31, "pairs trade only where both legs really traded"
    assert a.size == b.size == 31


def test_the_manifest_records_provenance_and_survives_a_round_trip(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    record = manifest.ArchiveRecord(
        source="binance_spot_klines",
        venue="binance",
        dataset="spot/klines",
        symbol="BTCUSDT",
        interval="1d",
        period="2021-08",
        url="https://data.binance.vision/x.zip",
        path="vendor/archive/binance/x.zip",
        size_bytes=2048,
        sha256="0" * 64,
        retrieved_at="2026-08-04T09:00:00+00:00",
    )

    manifest.append(cfg, record)
    (back,) = manifest.read_all(cfg)

    assert back == record
    assert back.venue != back.source, "whose prints, and which archive served them"


def test_a_zero_byte_download_counts_as_absent(tmp_path: Path) -> None:
    """An interrupted download must not masquerade as a complete one; trusting
    the path to merely exist is how a truncated month becomes a silent hole."""
    empty = tmp_path / "empty.zip"
    empty.write_bytes(b"")
    full = tmp_path / "full.zip"
    full.write_bytes(b"data")

    assert not manifest.already_have(empty)
    assert not manifest.already_have(tmp_path / "missing.zip")
    assert manifest.already_have(full)


def test_the_archive_source_is_declared_and_carries_no_fee_schedule() -> None:
    """ADR-031: an archive is not a venue. Publishing a fee schedule for one
    would invite a strategy to be modelled on fees no order of ours could pay —
    Binance is not legally available to Canadian residents at all."""
    cfg = load_config()

    source = cfg.sources["binance_spot_klines"]
    assert source.kind == "archive", "never left to default to recorder"
    assert source.venue == "binance"
    assert "binance" not in cfg.venues, "an archive must not appear as a tradeable venue"
    assert not hasattr(source, "fee_tiers")
