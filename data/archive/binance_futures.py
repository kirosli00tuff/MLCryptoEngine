"""Binance USD-M futures: funding history back to 2019, and the perp leg.

Hyperliquid is the venue the short would actually sit on, but it launched in
2023-05 and so cannot answer the question this stage most needs answered —
**has funding compressed over time?** A crowded, widely published trade should
show yield decay, and three years starting after the 2022 bear market is not
enough sample to see it. Binance perpetuals go back to 2019-09 and are free, so
they carry the decay analysis while Hyperliquid carries the tradeable numbers.

**Funding here is charged every EIGHT hours, not hourly.** That is the opposite
convention to Hyperliquid's, and the two are mixed constantly in the
literature. Every rate in this module is per eight-hour interval; annualising
uses 1,095 intervals a year, not 8,760.

Binance is not legally available to Canadian residents (CLAUDE.md hard
constraint). Nothing here is ever traded — it is history for a decay curve.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from data.archive import manifest
from data.archive.binance import CDN_HOST, months_between
from data.archive.http import NotFound, fetch_to_file
from data.config import AppConfig, SourceConfig

SOURCE_KEY = "binance_futures_archive"
FUNDING_PREFIX = "data/futures/um/monthly/fundingRate"
KLINE_PREFIX = "data/futures/um/monthly/klines"

# Eight-hourly. Contrast data.archive.hyperliquid.FUNDING_INTERVAL_MS, which is
# hourly for the same economic quantity on a different venue.
FUNDING_INTERVAL_MS = 8 * 3_600_000
FUNDING_INTERVALS_PER_YEAR = 365 * 3

COL_TIME, COL_SYMBOL, COL_RATE = 0, 1, 2


@dataclass(frozen=True)
class FundingRow:
    """One eight-hourly funding observation."""

    symbol: str
    time_ms: int
    rate: float

    @property
    def annualised(self) -> float:
        return self.rate * FUNDING_INTERVALS_PER_YEAR


def source_config(cfg: AppConfig) -> SourceConfig:
    source = cfg.sources.get(SOURCE_KEY)
    if source is None:
        raise KeyError(f"source '{SOURCE_KEY}' is not configured in config/venues.yaml")
    return source


def funding_url(symbol: str, period: str) -> str:
    return f"{CDN_HOST}/{FUNDING_PREFIX}/{symbol}/{symbol}-fundingRate-{period}.zip"


def funding_path(cfg: AppConfig, symbol: str, period: str) -> Path:
    return (
        manifest.archive_dir(cfg)
        / "binance"
        / "futures"
        / "fundingRate"
        / f"symbol={symbol}"
        / f"{symbol}-fundingRate-{period}.zip"
    )


def perp_kline_url(symbol: str, interval: str, period: str) -> str:
    return f"{CDN_HOST}/{KLINE_PREFIX}/{symbol}/{interval}/{symbol}-{interval}-{period}.zip"


def perp_kline_path(cfg: AppConfig, symbol: str, interval: str, period: str) -> Path:
    return (
        manifest.archive_dir(cfg)
        / "binance"
        / "futures"
        / "klines"
        / f"symbol={symbol}"
        / f"interval={interval}"
        / f"{symbol}-{interval}-{period}.zip"
    )


def _fetch(
    cfg: AppConfig, url: str, target: Path, dataset: str, symbol: str, interval: str, period: str
) -> Path | None:
    """Download one monthly file if absent. ``None`` when the archive has none."""
    if manifest.already_have(target):
        return target
    try:
        size, digest = fetch_to_file(url, target)
    except NotFound:
        return None
    source = source_config(cfg)
    manifest.append(
        cfg,
        manifest.ArchiveRecord(
            source=SOURCE_KEY,
            venue=source.venue,
            dataset=dataset,
            symbol=symbol,
            interval=interval,
            period=period,
            url=url,
            path=str(target.relative_to(cfg.data_root)),
            size_bytes=size,
            sha256=digest,
            retrieved_at=manifest.utc_stamp(),
        ),
    )
    return target


def fetch_funding_month(cfg: AppConfig, symbol: str, period: str) -> Path | None:
    return _fetch(
        cfg,
        funding_url(symbol, period),
        funding_path(cfg, symbol, period),
        "futures/fundingRate",
        symbol,
        "8h",
        period,
    )


def fetch_perp_kline_month(cfg: AppConfig, symbol: str, interval: str, period: str) -> Path | None:
    return _fetch(
        cfg,
        perp_kline_url(symbol, interval, period),
        perp_kline_path(cfg, symbol, interval, period),
        "futures/klines",
        symbol,
        interval,
        period,
    )


def read_funding_month(path: Path) -> list[FundingRow]:
    """Parse one monthly funding ZIP. Tolerates the header row newer files carry."""
    rows: list[FundingRow] = []
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".csv")]
        if not names:
            raise ValueError(f"{path} contains no CSV member")
        with archive.open(names[0]) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8")):
                if len(row) <= COL_RATE:
                    continue
                try:
                    time_ms = int(row[COL_TIME])
                    rate = float(row[COL_RATE])
                except ValueError:
                    continue  # header row
                rows.append(FundingRow(symbol=row[COL_SYMBOL], time_ms=time_ms, rate=rate))
    rows.sort(key=lambda r: r.time_ms)
    return rows


def load_funding(cfg: AppConfig, symbol: str, start: str, end: str) -> list[FundingRow]:
    """Every cached funding observation in ``[start, end]``, oldest first."""
    seen: dict[int, FundingRow] = {}
    for period in months_between(start, end):
        path = funding_path(cfg, symbol, period)
        if not manifest.already_have(path):
            continue
        for row in read_funding_month(path):
            seen[row.time_ms] = row
    return [seen[t] for t in sorted(seen)]
