"""Who was tradeable on each date, from the venue's own record of it.

C.10 built a point-in-time universe by asking which symbols had bars in the
sample's first month, and never consulting the end of the sample (ADR-029).
That rule was necessary because Binance's dump archive answers "does this
symbol have a file" and nothing else. Hyperliquid answers a better question, so
this module asks a better one.

**Membership is per day, not per sample.** A coin is in the universe on day D
if the venue published a funding rate for it on D *and* its book produced a
daily close on D. Both come from the venue, and together they are the venue's
own statement that the instrument was live and priceable that day. A coin that
listed in 2025 is simply absent before it listed; a coin delisted in 2024 is
present until it stops and absent after. Nothing is excluded by hand and no
rule refers to the end of the sample.

**What makes this survivorship-free rather than merely careful.** The venue
addresses perps by their index in the ``meta`` universe array, so a delisted
asset cannot be removed without renumbering every asset after it — it is
flagged in place and kept. The funding and candle endpoints keep serving its
full history. FTT, the FTX token, is in the array today with candles ending
2026-05-25; MATIC, UNIBOT and FRIEND are all still addressable. The pool this
study screens therefore contains the instruments whose funding went pathological
and then died, which is exactly the population a survivorship-biased universe
drops — and dropping them biases a *dispersion* measurement in the obvious
direction, because those are the extreme observations.

**The residual bias, stated rather than waved at.** If the venue ever purged an
asset from the array outright, it would be invisible here and no check in this
project could detect it. The evidence against is structural (positional
indices) and empirical (55 delisted entries retained, interspersed by listing
age rather than appended). That is evidence, not proof, and any residual bias
points toward **understating** dispersion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from data.archive import hyperliquid as hl
from research.cross.acquire import CoinHistory

DAYS_PER_YEAR = 365


def day_stamp(day_ms: int) -> str:
    return datetime.fromtimestamp(day_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def month_stamp(day_ms: int) -> str:
    return datetime.fromtimestamp(day_ms / 1000, tz=UTC).strftime("%Y-%m")


def year_of(day_ms: int) -> str:
    return datetime.fromtimestamp(day_ms / 1000, tz=UTC).strftime("%Y")


def annualise_daily(rate: float) -> float:
    """A one-day funding total expressed as an annual rate.

    Daily totals are already interval-agnostic — they are sums of whatever the
    venue charged that day, whether that was three eight-hourly rows or
    twenty-four hourly ones — so the only conversion needed is 365, and this is
    the single place it happens.
    """
    return rate * DAYS_PER_YEAR


@dataclass(frozen=True)
class Listing:
    """One instrument's observed life on the venue."""

    coin: str
    first_day_ms: int
    last_day_ms: int
    days_live: int
    is_delisted_now: bool

    def summary(self) -> dict[str, Any]:
        return {
            "coin": self.coin,
            "first": day_stamp(self.first_day_ms),
            "last": day_stamp(self.last_day_ms),
            "days_live": self.days_live,
            "delisted_now": self.is_delisted_now,
        }


@dataclass
class PerpUniverse:
    """Daily membership plus the evidence that it is point-in-time."""

    listings: dict[str, Listing] = field(default_factory=dict)
    # day (UTC-midnight epoch ms) -> coins the venue both funded and priced
    members: dict[int, set[str]] = field(default_factory=dict)
    considered: int = 0
    delisted_in_pool: int = 0

    @property
    def days(self) -> list[int]:
        return sorted(self.members)

    def size_by_month(self) -> dict[str, int]:
        """Mean instruments live per day in each month — the cross-section size.

        A monthly *mean* rather than a month-end count, because a month-end
        snapshot would miss a coin that listed and died inside the month, and
        those are the observations this universe exists to keep.
        """
        buckets: dict[str, list[int]] = {}
        for day, coins in self.members.items():
            buckets.setdefault(month_stamp(day), []).append(len(coins))
        return {m: round(sum(v) / len(v)) for m, v in sorted(buckets.items())}

    def deaths_in_sample(self) -> list[Listing]:
        """Instruments whose last funded day precedes the sample's last day."""
        if not self.members:
            return []
        end = max(self.members)
        return sorted(
            (listing for listing in self.listings.values() if listing.last_day_ms < end),
            key=lambda listing: listing.last_day_ms,
        )

    def summary(self) -> dict[str, Any]:
        sizes = self.size_by_month()
        dead = self.deaths_in_sample()
        by_month = list(sizes.values())
        return {
            "selection_rule": (
                "membership is per day: the venue published a funding rate AND a daily "
                "close for the instrument on that day. No rule consults the end of the "
                "sample, so a coin that died mid-sample is present until it died."
            ),
            "candidates_considered": self.considered,
            "delisted_instruments_in_pool": self.delisted_in_pool,
            "instruments_ever_live": len(self.listings),
            "died_in_sample": len(dead),
            "died_symbols": [listing.coin for listing in dead],
            "first_day": day_stamp(min(self.members)) if self.members else None,
            "last_day": day_stamp(max(self.members)) if self.members else None,
            "trading_days": len(self.members),
            "cross_section_min": min((len(c) for c in self.members.values()), default=0),
            "cross_section_max": max((len(c) for c in self.members.values()), default=0),
            "cross_section_first_month": by_month[0] if by_month else 0,
            "cross_section_last_month": by_month[-1] if by_month else 0,
            "size_by_month": sizes,
            "survivorship": (
                "Survivorship-free by construction. Hyperliquid addresses perps by their "
                "index in the meta universe array, so a delisted asset is flagged in place "
                "rather than removed, and the funding and candle endpoints keep serving "
                "its full history. Verified: FTT is present, candles ending 2026-05-25."
            ),
            "residual_bias": (
                "An asset purged from the array outright would be invisible here and no "
                "check in this project could detect it. Positional indices make that "
                "structurally unlikely and 55 retained delisted entries are the empirical "
                "evidence, but that is evidence and not proof. Any residual bias points "
                "toward UNDERSTATING dispersion, since the missing names are the extreme "
                "ones."
            ),
        }


def build(histories: dict[str, CoinHistory], assets: list[hl.PerpAsset]) -> PerpUniverse:
    """Daily membership across every instrument that produced usable history."""
    universe = PerpUniverse(
        considered=len(assets),
        delisted_in_pool=sum(1 for a in assets if a.is_delisted),
    )
    for coin, history in sorted(histories.items()):
        if not history.usable:
            continue
        live = sorted(set(history.funding_by_day()) & set(history.closes_by_day()))
        if not live:
            continue
        universe.listings[coin] = Listing(
            coin=coin,
            first_day_ms=live[0],
            last_day_ms=live[-1],
            days_live=len(live),
            is_delisted_now=history.is_delisted_now,
        )
        for day in live:
            universe.members.setdefault(day, set()).add(coin)
    return universe


def panels(
    histories: dict[str, CoinHistory], universe: PerpUniverse
) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    """Aligned ``(funding, price)`` panels restricted to live days.

    Both are ``coin -> day_ms -> value``. Restricting to universe membership
    here is what stops a downstream consumer reading a funding rate on a day the
    instrument had no price, or a price on a day it paid no funding.
    """
    funding: dict[str, dict[int, float]] = {}
    price: dict[str, dict[int, float]] = {}
    for coin, listing in universe.listings.items():
        history = histories[coin]
        funded, priced = history.funding_by_day(), history.closes_by_day()
        live = {
            d for d in funded if d in priced and listing.first_day_ms <= d <= listing.last_day_ms
        }
        funding[coin] = {d: v for d, v in funded.items() if d in live}
        price[coin] = {d: v for d, v in priced.items() if d in live}
    return funding, price


def cohort_listed_by(universe: PerpUniverse, day_ms: int) -> set[str]:
    """Instruments already live on ``day_ms`` — a fixed cohort for controls.

    Dispersion measured over all listed instruments confounds two things: the
    market's funding rates spreading out, and the venue adding thinner coins
    whose funding is wilder to begin with. Re-running the measurement on the
    cohort that existed at the start separates them.
    """
    return {coin for coin, listing in universe.listings.items() if listing.first_day_ms <= day_ms}
