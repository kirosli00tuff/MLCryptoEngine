"""Binance public dumps: the only free source that remembers dead assets.

This module exists for one reason. Screening today's liquid symbols over a
multi-year window silently deletes everything that died inside it, and dead
assets are precisely the ones whose price relationships broke — which is the
relationship a pairs study is measuring. A universe built that way does not
have a small bias; it has the bias pointed directly at its own conclusion.

``data.binance.vision`` retains delisted symbols. Verified 2026-08-04:
``FTTUSDT`` (FTX's token, exchange collapsed November 2022), ``LUNAUSDT``
(Terra, collapsed May 2022), ``SRMUSDT``, ``BUSDUSDT`` and ``WAVESUSDT`` all
still resolve. That makes a *point-in-time* universe constructible: list what
had bars in the first month of the sample, rank it by that month's volume, and
let whatever died die inside the sample where it belongs.

Neither Kraken's ``AssetPairs`` nor Coinbase's ``products`` can do this — both
enumerate only what trades today — which is why neither is ever used to select
a universe here, only to cross-check prices.

Caveat worth stating rather than assuming away: this rests on Binance not
purging delisted directories. Five known-dead symbols surviving is evidence,
not a guarantee, and a symbol purged before this ran would be invisible to the
check itself. See ADR-029.
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from data.archive import manifest
from data.archive.http import NotFound, fetch_bytes, fetch_to_file
from data.config import AppConfig, SourceConfig

SOURCE_KEY = "binance_spot_klines"
DATASET = "spot/klines"
CDN_HOST = "https://data.binance.vision"
# The S3 REST endpoint behind data.binance.vision. The CDN host serves objects
# but not listings, and listings are what the universe is built from.
LISTING_HOST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
KLINE_PREFIX = "data/spot/monthly/klines"
# USDT is the deepest and longest-running quote asset on this venue. Mixing
# quote assets would compare a USDT price series against a BUSD one and call
# the difference cointegration.
QUOTE = "USDT"
# Stablecoins and metal-pegged tokens quoted against USDT are cointegrated by
# construction: a peg is not a discovered relationship, and a study reporting
# USDC/USDT as its best pair has rediscovered the peg, not found an edge.
PEGGED = frozenset(
    {
        "USDC",
        "BUSD",
        "TUSD",
        "USDP",
        "DAI",
        "FDUSD",
        "EUR",
        "GBP",
        "AEUR",
        "USD1",
        "PAXG",
        "XAUT",
    }
)

# Binance kline CSV column order, stable since 2017.
COL_OPEN_TIME, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME = 0, 1, 2, 3, 4, 5
COL_QUOTE_VOLUME, COL_TRADES = 7, 8
# Open time is milliseconds in older dumps and microseconds in newer ones.
# Anything at or past this magnitude is microseconds; the alternative is
# silently reading a 2025 bar as a timestamp fifty thousand years out.
MICROSECOND_THRESHOLD = 1_000_000_000_000_000


@dataclass(frozen=True)
class Bar:
    """One OHLCV bar, times normalised to UTC nanoseconds."""

    open_ns: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int


def source_config(cfg: AppConfig) -> SourceConfig:
    source = cfg.sources.get(SOURCE_KEY)
    if source is None:
        raise KeyError(
            f"source '{SOURCE_KEY}' is not configured; add it to the sources block "
            "in config/venues.yaml"
        )
    return source


def _listing(prefix: str, delimiter: str) -> tuple[list[str], list[str], str | None]:
    """One page of an S3 listing: (common prefixes, keys, next marker)."""
    url = f"{LISTING_HOST}?delimiter={delimiter}&prefix={prefix}"
    root = ElementTree.fromstring(fetch_bytes(url))
    prefixes = [
        node.text for node in root.findall(".//s3:CommonPrefixes/s3:Prefix", S3_NS) if node.text
    ]
    keys = [node.text for node in root.findall(".//s3:Contents/s3:Key", S3_NS) if node.text]
    truncated = root.find("s3:IsTruncated", S3_NS)
    is_truncated = truncated is not None and truncated.text == "true"
    marker_node = root.find("s3:NextMarker", S3_NS)
    marker = marker_node.text if is_truncated and marker_node is not None else None
    if is_truncated and marker is None and keys:
        # A delimiter-less listing omits NextMarker; the last key is the marker.
        marker = keys[-1]
    return prefixes, keys, marker


def _listing_all(prefix: str, delimiter: str = "/") -> tuple[list[str], list[str]]:
    """Every page of an S3 listing, following the marker to the end."""
    all_prefixes: list[str] = []
    all_keys: list[str] = []
    marker: str | None = ""
    while marker is not None:
        page = f"{prefix}&marker={marker}" if marker else prefix
        prefixes, keys, marker = _listing(page, delimiter)
        all_prefixes.extend(prefixes)
        all_keys.extend(keys)
    return all_prefixes, all_keys


def list_symbols() -> list[str]:
    """Every spot symbol with a kline directory, listed and delisted alike."""
    prefixes, _ = _listing_all(f"{KLINE_PREFIX}/")
    head = f"{KLINE_PREFIX}/"
    return sorted(p[len(head) :].strip("/") for p in prefixes)


def candidate_symbols(symbols: list[str]) -> list[str]:
    """USDT-quoted symbols with the pegged and wrapped ones removed.

    Applied to the *full* listing rather than to today's tradeable set, so it
    narrows the universe without reintroducing survivorship.
    """
    out = []
    for symbol in symbols:
        # The listing carries a handful of non-ASCII promotional directories
        # ("币安人生USDT" and four siblings, seen 2026-08-04). One of them ends
        # in USDT and would otherwise enter the universe; it also breaks the
        # HTTP client, since urllib encodes request lines as ASCII. Real
        # Binance symbols are uppercase alphanumeric without exception.
        if not (symbol.isascii() and symbol.isalnum()):
            continue
        if not symbol.endswith(QUOTE):
            continue
        base = symbol[: -len(QUOTE)]
        if not base or base in PEGGED:
            continue
        out.append(symbol)
    return sorted(out)


def available_periods(symbol: str, interval: str) -> list[str]:
    """``YYYY-MM`` periods this symbol has a monthly file for, oldest first.

    This is the listing/delisting record. A symbol whose periods stop in
    2022-05 stopped trading then; it stays in the universe and its price series
    simply ends, which is the honest treatment of an asset that died.
    """
    prefix = f"{KLINE_PREFIX}/{symbol}/{interval}/"
    _, keys = _listing_all(prefix, delimiter="")
    stem, suffix = f"{symbol}-{interval}-", ".zip"
    periods = []
    for key in keys:
        name = key.rsplit("/", 1)[-1]
        if not (name.startswith(stem) and name.endswith(suffix)) or "CHECKSUM" in name:
            continue
        period = name[len(stem) : -len(suffix)]
        if len(period) == 7 and period[4] == "-":
            periods.append(period)
    return sorted(periods)


def month_url(symbol: str, interval: str, period: str) -> str:
    return f"{CDN_HOST}/{KLINE_PREFIX}/{symbol}/{interval}/{symbol}-{interval}-{period}.zip"


def month_path(cfg: AppConfig, symbol: str, interval: str, period: str) -> Path:
    return (
        manifest.archive_dir(cfg)
        / "binance"
        / "spot"
        / "klines"
        / f"symbol={symbol}"
        / f"interval={interval}"
        / f"{symbol}-{interval}-{period}.zip"
    )


def fetch_month(cfg: AppConfig, symbol: str, interval: str, period: str) -> Path | None:
    """Download one monthly ZIP if absent. ``None`` when the archive has none.

    A missing month is returned rather than raised: it is the normal state for
    every month before a symbol listed and after it died, and treating it as an
    error would make the common case exceptional.
    """
    target = month_path(cfg, symbol, interval, period)
    if manifest.already_have(target):
        return target
    url = month_url(symbol, interval, period)
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
            dataset=DATASET,
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


def _normalise_open_time(raw: int) -> int:
    """Kline open time in UTC nanoseconds, whatever unit the dump used."""
    return raw * 1_000 if raw >= MICROSECOND_THRESHOLD else raw * 1_000_000


def read_month(path: Path) -> list[Bar]:
    """Parse one monthly ZIP into bars, oldest first.

    Handles both dump generations: older files are bare CSV, newer ones carry a
    header row, and open time is milliseconds in one and microseconds in the
    other. Guessing wrong on either fails silently — a header row parses as a
    bar of NaNs, and a microsecond timestamp read as milliseconds lands in the
    year 51,000 — so both are detected rather than assumed.
    """
    bars: list[Bar] = []
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".csv")]
        if not names:
            raise ValueError(f"{path} contains no CSV member")
        with archive.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8")
            for row in csv.reader(text):
                if len(row) <= COL_TRADES:
                    continue
                try:
                    open_time = int(row[COL_OPEN_TIME])
                except ValueError:
                    continue  # header row
                bars.append(
                    Bar(
                        open_ns=_normalise_open_time(open_time),
                        open=float(row[COL_OPEN]),
                        high=float(row[COL_HIGH]),
                        low=float(row[COL_LOW]),
                        close=float(row[COL_CLOSE]),
                        volume=float(row[COL_VOLUME]),
                        quote_volume=float(row[COL_QUOTE_VOLUME]),
                        trades=int(float(row[COL_TRADES])),
                    )
                )
    bars.sort(key=lambda b: b.open_ns)
    return bars


def months_between(start: str, end: str) -> list[str]:
    """Inclusive ``YYYY-MM`` sequence."""
    start_date = datetime.strptime(start, "%Y-%m").replace(tzinfo=UTC).date()
    end_date = datetime.strptime(end, "%Y-%m").replace(tzinfo=UTC).date()
    if end_date < start_date:
        raise ValueError(f"end {end} precedes start {start}")
    out: list[str] = []
    cursor = start_date
    while cursor <= end_date:
        out.append(cursor.strftime("%Y-%m"))
        cursor = (
            date(cursor.year + 1, 1, 1)
            if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )
    return out
