"""Pull free funding and daily-price history for the whole perp universe.

Nothing here is purchased. The Hyperliquid info endpoint is unauthenticated and
free, so the cost gate of ADR-017 does not apply — but "free" is not
"unlimited", so this module is deliberately slow: a weight-based limiter allows
roughly 1,200 weight per minute per IP and a ``fundingHistory`` call costs 20 of
it, which is about one request a second. Three live recorders share this host's
network and matter more than a backfill finishing sooner.

Two properties make the download tractable across 232 instruments.

**Daily candles cover the sample in one request.** The page limit is 5,000
*bars*, not 5,000 hours. C.11 needed hourly prices and concluded the endpoint
"cannot cover the sample" — true at ``1h``, which reaches 208 days, and false at
``1d``, where 5,000 bars is 13.7 years against a 3.2 year history. That is why
this stage prices both legs from Hyperliquid's own book rather than
reconstructing them from Binance spot, and it is why HYPE and MERL — which have
no Binance spot listing and so could not be modelled in C.11 at all — are
priceable here.

**Funding is the expensive half and is partly cached already.** 500 rows a page
against ~28,000 hourly rows for a coin listed since launch is ~57 requests; the
12 perps C.11 fetched are reused from disk. The whole job is resumable, because
a full page is immutable once written and only the short tail page is ever
re-requested.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from data.archive import hyperliquid as hl
from data.archive.http import ArchiveFetchError
from data.config import AppConfig

# Daily bars: one page covers 13.7 years, so price history is one request a coin.
PRICE_INTERVAL = "1d"
MS_PER_DAY = 86_400_000
# An instrument with less history than this can contribute neither a trailing
# signal nor a holding period. Such coins are still downloaded and still
# counted, with the reason recorded — a name that vanishes from a study without
# appearing in its exclusion count is the survivorship hole in miniature.
MIN_FUNDING_DAYS = 30


@dataclass
class CoinHistory:
    """Everything the study needs about one instrument, or why it has nothing."""

    coin: str
    is_delisted_now: bool
    funding: list[hl.FundingRow] = field(default_factory=list)
    candles: list[hl.Candle] = field(default_factory=list)
    error: str = ""

    @property
    def usable(self) -> bool:
        """Enough funding *and* enough price to be both rankable and tradeable."""
        if self.error or not self.funding or not self.candles:
            return False
        span_ms = self.funding[-1].time_ms - self.funding[0].time_ms
        return span_ms >= MIN_FUNDING_DAYS * MS_PER_DAY

    def closes_by_day(self) -> dict[int, float]:
        """Daily close keyed by the bar's UTC-midnight open, as epoch ms."""
        return {c.open_ms: c.close for c in self.candles if c.close > 0}

    def funding_by_day(self) -> dict[int, float]:
        """Funding actually charged each UTC day, summed over its intervals.

        A sum is correct here where a mean would not be: each row is the rate
        charged for its own interval, so the sum is what the day really paid.
        It also crosses the venue's 2023-06-08 switch from eight-hourly to
        hourly funding without needing a per-interval constant, since three 8h
        rows and 24 1h rows both sum to that day's realised cost.
        """
        out: dict[int, float] = {}
        for row in self.funding:
            day = row.time_ms - (row.time_ms % MS_PER_DAY)
            out[day] = out.get(day, 0.0) + row.rate
        return out


def fetch_coin(cfg: AppConfig, asset: hl.PerpAsset, end_ms: int) -> CoinHistory:
    """Funding and daily candles for one instrument, cached pages reused.

    A fetch failure is captured on the record rather than raised. One dead
    instrument out of 232 must not abort a multi-hour download, and a coin that
    disappeared from the study without explanation is exactly the hole this
    stage exists to avoid — so the reason travels with the record and is
    reported.
    """
    history = CoinHistory(coin=asset.name, is_delisted_now=asset.is_delisted)
    try:
        history.funding = hl.fetch_funding(cfg, asset.name)
    except (ArchiveFetchError, ValueError, KeyError) as exc:
        history.error = f"funding: {type(exc).__name__}: {exc}"
        return history
    try:
        history.candles = hl.fetch_candles(
            cfg, asset.name, hl.GENESIS_MS, end_ms, interval=PRICE_INTERVAL
        )
    except (ArchiveFetchError, ValueError, KeyError) as exc:
        history.error = f"candles: {type(exc).__name__}: {exc}"
    return history


def fetch_all(
    cfg: AppConfig, end_ms: int, limit: int | None = None, verbose: bool = True
) -> tuple[list[hl.PerpAsset], dict[str, CoinHistory]]:
    """The whole universe: every perp the venue has listed, live or delisted."""
    assets = hl.fetch_universe(cfg)
    if limit is not None:
        assets = assets[:limit]
    out: dict[str, CoinHistory] = {}
    started = time.monotonic()
    for i, asset in enumerate(assets, start=1):
        history = fetch_coin(cfg, asset, end_ms)
        out[asset.name] = history
        if verbose:
            print(
                f"[{i:3d}/{len(assets)}] {asset.name:<12s} "
                f"funding={len(history.funding):6d} candles={len(history.candles):5d} "
                f"{'DELISTED' if asset.is_delisted else '        '} "
                f"{history.error}({time.monotonic() - started:.0f}s)",
                flush=True,
            )
    return assets, out


def coverage(assets: list[hl.PerpAsset], histories: dict[str, CoinHistory]) -> dict[str, Any]:
    """What the download obtained, including what it could not.

    Reports the pool considered beside the pool kept, per ADR-030: a screen
    that publishes only its survivors cannot be audited for what it discarded.
    """
    usable = [h for h in histories.values() if h.usable]
    failed = [h for h in histories.values() if h.error]
    return {
        "instruments_in_venue_universe": len(assets),
        "delisted_now": sum(1 for a in assets if a.is_delisted),
        "live_now": sum(1 for a in assets if not a.is_delisted),
        "downloaded": len(histories),
        "usable": len(usable),
        "usable_delisted": sum(1 for h in usable if h.is_delisted_now),
        "excluded_short_history": sum(
            1 for h in histories.values() if not h.usable and not h.error
        ),
        "min_funding_days_required": MIN_FUNDING_DAYS,
        "failed": {h.coin: h.error for h in failed},
        "funding_rows_total": sum(len(h.funding) for h in histories.values()),
        "price_source": (
            "Hyperliquid daily candles from the venue's own book, not Binance spot. Both "
            "legs of this trade sit on Hyperliquid, so its own price is the correct one, "
            "and 5,000 daily bars covers the sample in a single request per coin."
        ),
    }
