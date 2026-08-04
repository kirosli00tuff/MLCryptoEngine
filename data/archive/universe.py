"""Point-in-time universe construction: who was listed when the sample began.

The selection rule is one sentence, and every clause is load-bearing: **the
symbols that had bars in the first month of the sample, ranked by that month's
quote volume.** Not today's liquid symbols; not symbols with a complete series;
not symbols that are still trading. Each of those alternatives is a way of
letting the sample's end leak into its beginning.

What this buys, concretely. Over 2021-08 to 2026-07 the crypto universe lost
Terra (LUNA, May 2022) and FTX's token (FTT, November 2022), among others. Both
were major assets at the start of that window. A universe screened on today's
liquidity contains neither, so a pairs study over that window would never test
a relationship that ended in a total collapse — while quietly keeping every
relationship that survived. Measured cointegration decay would then be an
artefact of the screen rather than a property of the market.

Members that die mid-sample stay in, and their price series simply ends. That
is not a data-quality problem to be patched; it is the event the study most
needs to see.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.archive import binance
from data.archive.http import MAX_CONCURRENCY
from data.config import AppConfig

# Selection runs on daily bars so the volume ranking cannot depend on which
# interval the study later chooses to trade.
SELECTION_INTERVAL = "1d"


@dataclass(frozen=True)
class Member:
    """One universe member and its life span within the archive."""

    symbol: str
    selection_quote_volume: float
    first_period: str
    last_period: str

    def died_before(self, end_period: str) -> bool:
        """True if the symbol stopped producing bars before the sample ended."""
        return self.last_period < end_period


@dataclass
class Universe:
    """A point-in-time universe plus the evidence that it is one."""

    start_period: str
    end_period: str
    members: list[Member] = field(default_factory=list)
    candidates_considered: int = 0
    listed_at_start: int = 0
    selection_rule: str = (
        "symbols with a Binance monthly daily-bar file in the sample's FIRST month, "
        "ranked by that month's quote volume — never by today's liquidity"
    )

    @property
    def symbols(self) -> list[str]:
        return [m.symbol for m in self.members]

    def deaths(self) -> list[Member]:
        """Members whose bars stop before the sample ends."""
        return [m for m in self.members if m.died_before(self.end_period)]

    def summary(self) -> dict[str, Any]:
        dead = self.deaths()
        return {
            "start_period": self.start_period,
            "end_period": self.end_period,
            "candidates_considered": self.candidates_considered,
            "listed_at_start": self.listed_at_start,
            "selected": len(self.members),
            "died_in_sample": len(dead),
            "died_symbols": [m.symbol for m in dead],
            "selection_rule": self.selection_rule,
            "survivorship_free": True,
            "survivorship_caveat": (
                "Rests on Binance retaining delisted symbol directories, verified for "
                "FTTUSDT, LUNAUSDT, SRMUSDT, BUSDUSDT and WAVESUSDT on 2026-08-04. A "
                "symbol purged before that date would be invisible to this check."
            ),
        }


def _month_quote_volume(cfg: AppConfig, symbol: str, period: str) -> tuple[str, float | None]:
    """Total quote volume for one symbol-month, or ``None`` if it has no file.

    ``None`` is the listing test: no file for the sample's first month means
    the symbol was not trading then and is not in the universe, regardless of
    how large it later became. Admitting it on the strength of its later size
    is precisely the look-ahead this module exists to prevent.
    """
    path = binance.fetch_month(cfg, symbol, SELECTION_INTERVAL, period)
    if path is None:
        return symbol, None
    bars = binance.read_month(path)
    if not bars:
        return symbol, None
    return symbol, sum(b.quote_volume for b in bars)


def build(
    cfg: AppConfig,
    start_period: str,
    end_period: str,
    size: int,
    candidates: list[str] | None = None,
) -> Universe:
    """Select the top ``size`` symbols by quote volume in ``start_period``."""
    pool = (
        candidates if candidates is not None else binance.candidate_symbols(binance.list_symbols())
    )
    universe = Universe(start_period=start_period, end_period=end_period)
    universe.candidates_considered = len(pool)

    volumes: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        for symbol, volume in executor.map(
            lambda s: _month_quote_volume(cfg, s, start_period), pool
        ):
            if volume is not None and volume > 0.0:
                volumes[symbol] = volume
    universe.listed_at_start = len(volumes)

    ranked = sorted(volumes.items(), key=lambda kv: kv[1], reverse=True)[:size]
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        period_lists = list(
            executor.map(lambda kv: binance.available_periods(kv[0], SELECTION_INTERVAL), ranked)
        )
    for (symbol, volume), periods in zip(ranked, period_lists, strict=True):
        in_sample = [p for p in periods if start_period <= p <= end_period]
        if not in_sample:
            continue
        universe.members.append(
            Member(
                symbol=symbol,
                selection_quote_volume=volume,
                first_period=in_sample[0],
                last_period=in_sample[-1],
            )
        )
    return universe


def fetch_history(
    cfg: AppConfig, universe: Universe, interval: str, symbols: list[str] | None = None
) -> dict[str, list[Path]]:
    """Download every monthly file in range for the given symbols.

    Months the archive does not have are skipped silently — that is a symbol
    that had not listed yet or had already died, not a failure.
    """
    periods = binance.months_between(universe.start_period, universe.end_period)
    wanted = symbols if symbols is not None else universe.symbols
    jobs = [(symbol, period) for symbol in wanted for period in periods]
    out: dict[str, list[Path]] = {symbol: [] for symbol in wanted}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        for symbol, path in executor.map(
            lambda job: (job[0], binance.fetch_month(cfg, job[0], interval, job[1])), jobs
        ):
            if path is not None:
                out[symbol].append(path)
    return {symbol: sorted(paths) for symbol, paths in out.items()}
