"""Hyperliquid funding and perp candles — the venue the short leg would sit on.

This is the primary source for a carry study rather than a cross-check, because
Hyperliquid is the only venue reachable from British Columbia that offers a
short. Two of its properties decide the arithmetic, so both are stated once:

**Funding is charged hourly — but it was NOT always.** The observed baseline of
``0.00125%`` per hour is exactly one eighth of the ``0.01%/8h`` figure the
literature quotes, so both annualise to about 10.95%, and reading one as the
other misstates yield by 8x in either direction. Worse, the venue **changed its
own interval**: BTC funding rows are spaced eight hours apart from launch on
2023-05-12 until 2023-06-08, and hourly from then on (81 eight-hour steps, then
27,676 one-hour steps, plus three two-hour gaps).

So there is no correct constant. Anything that annualises this series by
multiplying a mean rate by a fixed intervals-per-year figure is wrong for part
of it, silently. Annualisation must divide accumulated funding by **elapsed
time**, which is interval-agnostic and also correct across the venue's outage
gaps. :func:`accumulated` and :func:`elapsed_years` exist so callers cannot get
this wrong by reaching for a constant; ``FundingRow`` deliberately exposes no
``annualised`` property of its own, because a single row does not know how long
it covered.

**History begins 2023-05-12**, the venue's launch. Nothing earlier exists at any
price, which bounds what any regime claim here can cover.

The endpoint is an unauthenticated POST JSON API with hard page limits: 500 rows
per ``fundingHistory`` call and 5,000 per ``candleSnapshot``. Both are paged,
and every raw page is stored immutably with its own manifest line, so the
normalised series can always be rebuilt from what the venue actually returned.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import orjson

from data.archive import manifest
from data.archive.http import POLITE_API_DELAY_S, post_bytes
from data.config import AppConfig, SourceConfig

SOURCE_KEY = "hyperliquid_info"
INFO_URL = "https://api.hyperliquid.xyz/info"
FUNDING_DATASET = "info/fundingHistory"
CANDLE_DATASET = "info/candleSnapshot"

# Hourly. See the module docstring — this is the constant most likely to be
# wrong by a factor of eight if it is ever inferred rather than read.
FUNDING_INTERVAL_MS = 3_600_000
MS_PER_YEAR = 365 * 24 * 3_600_000
# An interval longer than this is the venue not publishing, not a long funding
# period, and the time is excluded from the elapsed denominator rather than
# credited with the neighbouring rate.
MAX_CREDITED_INTERVAL_MS = 8 * 3_600_000
FUNDING_PAGE_LIMIT = 500
CANDLE_PAGE_LIMIT = 5_000
# Venue launch; nothing exists before this.
GENESIS_MS = 1_683_849_600_000  # 2023-05-12T00:00:00Z


@dataclass(frozen=True)
class FundingRow:
    """One hourly funding observation.

    ``rate`` is the fraction paid by longs to shorts over one hour. Positive
    means longs pay, which is the direction a short-perp carry collects.
    ``premium`` is the venue's mark-to-index premium that drives it.
    """

    coin: str
    time_ms: int
    rate: float
    premium: float


@dataclass(frozen=True)
class Candle:
    """One perp OHLCV bar from the venue's own book."""

    coin: str
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def source_config(cfg: AppConfig) -> SourceConfig:
    source = cfg.sources.get(SOURCE_KEY)
    if source is None:
        raise KeyError(f"source '{SOURCE_KEY}' is not configured in config/venues.yaml")
    return source


def _page_path(cfg: AppConfig, dataset: str, coin: str, key: str) -> Path:
    return (
        manifest.archive_dir(cfg) / "hyperliquid" / dataset / f"coin={coin}" / f"start={key}.json"
    )


def _record_page(
    cfg: AppConfig, dataset: str, coin: str, interval: str, key: str, path: Path, body: bytes
) -> None:
    source = source_config(cfg)
    manifest.append(
        cfg,
        manifest.ArchiveRecord(
            source=SOURCE_KEY,
            venue=source.venue,
            dataset=dataset,
            symbol=coin,
            interval=interval,
            period=key,
            url=INFO_URL,
            path=str(path.relative_to(cfg.data_root)),
            size_bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            retrieved_at=manifest.utc_stamp(),
        ),
    )


def _fetch_page(
    cfg: AppConfig, dataset: str, coin: str, interval: str, key: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """One page, from cache when complete, otherwise from the endpoint.

    A cached page is reused only when it is *full*. A short page is the tail of
    the series and grows as the venue produces more rows, so caching it would
    freeze the study's end date silently — the data would look complete and
    simply stop.
    """
    path = _page_path(cfg, dataset, coin, key)
    limit = FUNDING_PAGE_LIMIT if dataset == FUNDING_DATASET else CANDLE_PAGE_LIMIT
    if manifest.already_have(path):
        cached: list[dict[str, Any]] = orjson.loads(path.read_bytes())
        if len(cached) >= limit:
            return cached
    body = post_bytes(INFO_URL, orjson.dumps(payload), delay_s=POLITE_API_DELAY_S)
    rows: list[dict[str, Any]] = orjson.loads(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    _record_page(cfg, dataset, coin, interval, key, path, body)
    return rows


def fetch_funding(
    cfg: AppConfig, coin: str, start_ms: int = GENESIS_MS, end_ms: int | None = None
) -> list[FundingRow]:
    """Every hourly funding observation for one coin, oldest first.

    Pages forward from ``start_ms`` until the endpoint stops returning a full
    page. Duplicate timestamps across page boundaries are collapsed rather than
    summed — double-counting an interval inflates annualised yield by the
    fraction of the sample that sits on a boundary.
    """
    seen: dict[int, FundingRow] = {}
    cursor = start_ms
    while True:
        payload = {"type": "fundingHistory", "coin": coin, "startTime": cursor}
        rows = _fetch_page(cfg, FUNDING_DATASET, coin, "1h", str(cursor), payload)
        if not rows:
            break
        for row in rows:
            time_ms = int(row["time"])
            if end_ms is not None and time_ms > end_ms:
                continue
            seen[time_ms] = FundingRow(
                coin=str(row.get("coin", coin)),
                time_ms=time_ms,
                rate=float(row["fundingRate"]),
                premium=float(row.get("premium", "nan")),
            )
        last = int(rows[-1]["time"])
        if len(rows) < FUNDING_PAGE_LIMIT or last <= cursor:
            break
        cursor = last + 1
        if end_ms is not None and cursor > end_ms:
            break
    return [seen[t] for t in sorted(seen)]


def intervals_ms(rows: list[FundingRow]) -> list[int]:
    """How long each row's rate was in force, in milliseconds.

    Taken from the gap to the *next* row, since that is what the row actually
    covered; the last row inherits the previous gap because its own is unknown.
    Gaps beyond :data:`MAX_CREDITED_INTERVAL_MS` are venue outages and are
    clamped, so a two-day publication hole cannot be credited as two days of
    the rate that happened to precede it.
    """
    if not rows:
        return []
    if len(rows) == 1:
        return [FUNDING_INTERVAL_MS]
    gaps = [min(b.time_ms - a.time_ms, MAX_CREDITED_INTERVAL_MS) for a, b in pairwise(rows)]
    return [*gaps, gaps[-1]]


def accumulated(rows: list[FundingRow]) -> float:
    """Total funding collected per unit of notional over the whole series.

    A plain sum, because each row is the rate actually charged for its own
    interval. This is the numerator of any honest annualisation.
    """
    return sum(r.rate for r in rows)


def elapsed_years(rows: list[FundingRow]) -> float:
    """Covered time in years, from the realised intervals rather than a count."""
    return sum(intervals_ms(rows)) / MS_PER_YEAR


def annualised(rows: list[FundingRow]) -> float:
    """Accumulated funding divided by elapsed time. The only correct form here.

    Interval-agnostic by construction, so it survives both the venue's
    2023-06-08 switch from eight-hourly to hourly funding and its publication
    gaps, neither of which a fixed intervals-per-year constant survives.
    """
    years = elapsed_years(rows)
    return accumulated(rows) / years if years > 0 else 0.0


def fetch_candles(
    cfg: AppConfig, coin: str, start_ms: int, end_ms: int, interval: str = "1h"
) -> list[Candle]:
    """Perp OHLCV bars for one coin, oldest first, paged to the end."""
    span = FUNDING_INTERVAL_MS * CANDLE_PAGE_LIMIT
    seen: dict[int, Candle] = {}
    cursor = start_ms
    while cursor < end_ms:
        stop = min(cursor + span, end_ms)
        payload = {
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval, "startTime": cursor, "endTime": stop},
        }
        rows = _fetch_page(cfg, CANDLE_DATASET, coin, interval, str(cursor), payload)
        for row in rows:
            open_ms = int(row["t"])
            seen[open_ms] = Candle(
                coin=coin,
                open_ms=open_ms,
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
                volume=float(row["v"]),
            )
        cursor = stop
    return [seen[t] for t in sorted(seen)]
