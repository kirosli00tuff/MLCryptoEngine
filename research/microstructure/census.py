"""One streaming pass over recorded Hyperliquid data: spreads and adverse selection.

Both measurements consume the same two channels — ``bbo`` for quotes and
``trades`` for aggressor-signed prints — so they share a single pass. Nothing
day-sized is retained: each instrument holds a weighted histogram and a bounded
queue of trades awaiting their horizon.

Ordering is the recorder's local receive clock (``recv_ns``), the same clock
the rest of the pipeline orders on. Hyperliquid also stamps its own ``time``
field per message; that is the venue's clock and is never ordered against the
recorder's, per the standing rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

from data.recorder.reader import iter_day_records
from research.microstructure.adverse import DEFAULT_HORIZONS_MS, AdverseSelection
from research.microstructure.spread import SpreadCensus

# Hyperliquid marks the aggressor on each print: "B" when the buyer lifted the
# offer, "A" when the seller hit the bid. This is a venue flag, not inferred by
# a tick rule (see research/features/signing.py SIGNING_METHOD).
AGGRESSOR_SIGN: dict[str, int] = {"B": 1, "A": -1}


@dataclass
class InstrumentCensus:
    """Both accumulators for one instrument."""

    symbol: str
    spread: SpreadCensus
    adverse: AdverseSelection

    @classmethod
    def for_symbol(cls, symbol: str, horizons_ms: tuple[int, ...]) -> InstrumentCensus:
        return cls(
            symbol=symbol,
            spread=SpreadCensus(symbol=symbol),
            adverse=AdverseSelection(symbol=symbol, horizons_ms=horizons_ms),
        )


@dataclass
class CensusResult:
    """Accumulated census across one or more recorded days."""

    instruments: dict[str, InstrumentCensus] = field(default_factory=dict)
    records: int = 0
    bbo_messages: int = 0
    trade_messages: int = 0
    unparseable: int = 0

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "spread": self.instruments[symbol].spread.summary(),
                "adverse": self.instruments[symbol].adverse.summary(),
            }
            for symbol in sorted(self.instruments)
        ]


def _quote(bbo: list[Any]) -> tuple[float, float] | None:
    """``(bid, ask)`` from a Hyperliquid bbo pair, or None if either side is empty."""
    if len(bbo) != 2 or bbo[0] is None or bbo[1] is None:
        return None
    try:
        return float(bbo[0]["px"]), float(bbo[1]["px"])
    except (KeyError, TypeError, ValueError):
        return None


def run_census(
    raw_dir: Path,
    date: str,
    venue: str = "hyperliquid",
    horizons_ms: tuple[int, ...] = DEFAULT_HORIZONS_MS,
    result: CensusResult | None = None,
    coins: set[str] | None = None,
) -> CensusResult:
    """Accumulate spread and adverse-selection statistics for one recorded day.

    Pass an existing ``result`` to accumulate across days: the histograms and
    running sums are additive, so a multi-day census is the same object fed
    each day in order.

    ``coins`` restricts accumulation to an allowlist. ``None`` keeps the C.9
    behaviour (every coin in the stream). The restriction exists for C.18's
    hard rule: the known-answer validation runs on BTC and ETH only, and the
    ten thin instruments must not be *computed on* — not ingested-and-
    discarded, not summarised, not touched — before their census runs.
    """
    result = result if result is not None else CensusResult()
    last_ns = 0
    for recv_ns, raw in iter_day_records(raw_dir, venue, date):
        result.records += 1
        last_ns = recv_ns
        try:
            message = orjson.loads(raw)
        except orjson.JSONDecodeError:
            result.unparseable += 1
            continue
        channel = message.get("channel")
        data = message.get("data")
        if channel == "bbo" and isinstance(data, dict):
            symbol = data.get("coin")
            quote = _quote(data.get("bbo") or [])
            if not isinstance(symbol, str) or quote is None:
                continue
            if coins is not None and symbol not in coins:
                continue
            result.bbo_messages += 1
            inst = result.instruments.setdefault(
                symbol, InstrumentCensus.for_symbol(symbol, horizons_ms)
            )
            bid, ask = quote
            inst.spread.observe(recv_ns, bid, ask)
            if bid > 0.0 and ask > 0.0:
                inst.adverse.on_mid(recv_ns, 0.5 * (bid + ask))
        elif channel == "trades" and isinstance(data, list):
            result.trade_messages += 1
            for print_ in data:
                if not isinstance(print_, dict):
                    continue
                symbol = print_.get("coin")
                sign = AGGRESSOR_SIGN.get(str(print_.get("side")))
                if not isinstance(symbol, str) or sign is None:
                    continue
                if coins is not None and symbol not in coins:
                    continue
                inst = result.instruments.setdefault(
                    symbol, InstrumentCensus.for_symbol(symbol, horizons_ms)
                )
                inst.adverse.on_trade(recv_ns, sign)

    for inst in result.instruments.values():
        inst.spread.close(last_ns)
    return result
