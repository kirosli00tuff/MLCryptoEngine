"""An independent reference for the D.1d order machine, for differential testing.

The D.1d known-answer gate compared :class:`BoundedQuoteSim` in *generous* mode
against D.1c's ``InventorySim``. Audit finding A1 showed that check executes none
of the order machine — 106 lines covering ALO rejection, cancel latency, stale
crossing, placement and fill booking ran zero times under it. It validated the
ledger D.1d inherited, not the model D.1d added.

This module is the replacement control. It re-implements the registered D.1d
policy from its written statement rather than from ``fill_replay``'s code, and
it is deliberately structured differently in two ways that matter:

1. **The order machine is explicit and stateful per order.** Orders live in a
   list of :class:`_RefOrder` records carrying their own lifecycle timestamps,
   and each event walks that list. ``fill_replay`` keeps at most one order per
   side in a dict and mutates it in place.
2. **The ledger is recomputed from a blotter, not accumulated in flight.** The
   simulation emits ``(ts, side, price, size, mark_mid)`` rows; edge, fees and
   net are derived from those rows afterwards, in a second pass.
   ``fill_replay`` accumulates every term incrementally inside ``_settle``. Two
   different arithmetic routes to the same identity.

It is slow, allocates freely, and is used by no stage driver. Its only job is to
disagree with ``BoundedQuoteSim`` if either implementation is wrong.

**What this does and does not buy.** It is a genuine differential control over
the fill logic and the ledger arithmetic: a transcription slip, an inverted
comparison, or a mis-ordered lifecycle transition in either implementation shows
up as a mismatch. It is *not* independent in the strongest sense — both were
written by the same author from the same registered policy, so a misreading of
the policy itself would be reproduced in both. That limit is stated in
report.md §D.1d.1 rather than papered over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from research.microstructure.tick import tick_size

Event = tuple[Any, ...]
RefQueueModel = Literal["own_level", "own_level_cancels"]


@dataclass
class _RefOrder:
    side: str
    price: float
    size: float
    active_ns: int
    queue_ahead: float
    alo_checked: bool = False
    cancel_lands_ns: int | None = None
    dead: bool = False


@dataclass
class _Blot:
    ts_ns: int
    side: str
    price: float
    size: float
    mark_mid: float
    reason: str


@dataclass
class ReferenceQuoteSim:
    """The registered always-last policy, restated. Not for production use."""

    quote_size: float
    cap_size: float | None
    latency_ns: int
    sz_decimals: int
    queue_model: RefQueueModel = "own_level"
    maker_fee_bps: float = 1.5

    blotter: list[_Blot] = field(default_factory=list)
    alo_rejections: int = 0
    placements: int = 0
    cancels_started: int = 0
    _orders: list[_RefOrder] = field(default_factory=list)
    _mid: float | None = None
    _bid: float = 0.0
    _ask: float = 0.0
    _inventory_usd: float = 0.0
    _position: float = 0.0

    # ------------------------------------------------------------ helpers --
    def _live(self, side: str, ts_ns: int) -> _RefOrder | None:
        for o in self._orders:
            if o.side == side and not o.dead and o.active_ns <= ts_ns:
                return o
        return None

    def _pending(self, side: str) -> _RefOrder | None:
        for o in self._orders:
            if o.side == side and not o.dead:
                return o
        return None

    @staticmethod
    def _signed(side: str) -> int:
        return 1 if side == "bid" else -1

    def _headroom(self, side: str) -> float:
        if self.cap_size is None:
            return float("inf")
        return max(0.0, self.cap_size - self._signed(side) * self._position)

    def _book_fill(self, ts_ns: int, order: _RefOrder, want: float, reason: str) -> None:
        assert self._mid is not None
        size = min(want, self._headroom(order.side))
        if size > 0.0:
            self.blotter.append(_Blot(ts_ns, order.side, order.price, size, self._mid, reason))
            self._position += self._signed(order.side) * size
        order.dead = True

    def _sweep_dead(self) -> None:
        self._orders = [o for o in self._orders if not o.dead]

    def _transitions(self, ts_ns: int, bid: float, ask: float) -> set[str]:
        rejected: set[str] = set()
        for o in self._orders:
            if o.dead:
                continue
            if o.cancel_lands_ns is not None and o.cancel_lands_ns <= ts_ns:
                o.dead = True
                continue
            if o.active_ns <= ts_ns and not o.alo_checked:
                o.alo_checked = True
                would_cross = o.price >= ask if o.side == "bid" else o.price <= bid
                if would_cross:
                    self.alo_rejections += 1
                    o.dead = True
                    rejected.add(o.side)
        return rejected

    # ------------------------------------------------------------- events --
    def bbo(self, ts_ns: int, bid: float, bid_sz: float, ask: float, ask_sz: float) -> None:
        if bid <= 0.0 or ask <= 0.0 or ask <= bid:
            return
        mid = 0.5 * (bid + ask)
        if self._mid is not None:
            self._inventory_usd += self._position * (mid - self._mid)
        self._mid = mid

        rejected = self._transitions(ts_ns, bid, ask)

        # The opposing touch has run over a stale quote.
        for side in ("bid", "ask"):
            o = self._live(side, ts_ns)
            if o is None:
                continue
            run_over = ask <= o.price if side == "bid" else bid >= o.price
            if run_over:
                self._book_fill(ts_ns, o, o.size, "crossing")

        # The touch left our price, or the cap withdrew the side.
        for side in ("bid", "ask"):
            o = self._live(side, ts_ns)
            if o is None or o.cancel_lands_ns is not None:
                continue
            target = bid if side == "bid" else ask
            if o.price != target or self._headroom(side) <= 0.0:
                o.cancel_lands_ns = ts_ns + self.latency_ns
                self.cancels_started += 1

        # Cancellations ahead of us, where the feed can see them.
        if self.queue_model == "own_level_cancels":
            for side, tpx, tsz in (("bid", bid, bid_sz), ("ask", ask, ask_sz)):
                o = self._live(side, ts_ns)
                if o is not None and o.price == tpx:
                    o.queue_ahead = min(o.queue_ahead, tsz)

        # Quote whichever side is empty and permitted.
        for side in ("bid", "ask"):
            if self._pending(side) is not None or side in rejected:
                continue
            if self._headroom(side) <= 0.0:
                continue
            self._orders.append(
                _RefOrder(
                    side=side,
                    price=bid if side == "bid" else ask,
                    size=self.quote_size,
                    active_ns=ts_ns + self.latency_ns,
                    queue_ahead=bid_sz if side == "bid" else ask_sz,
                )
            )
            self.placements += 1

        self._bid, self._ask = bid, ask
        self._sweep_dead()

    def trade(self, ts_ns: int, aggressor_sign: int, px: float, sz: float) -> None:
        if self._mid is None or self._bid <= 0.0 or self._ask <= 0.0:
            return
        self._transitions(ts_ns, self._bid, self._ask)
        self._sweep_dead()

        side = "ask" if aggressor_sign > 0 else "bid"
        o = self._live(side, ts_ns)
        if o is None:
            return
        eps = 0.5 * tick_size(self._mid, self.sz_decimals)
        if (px > o.price + eps) if side == "ask" else (px < o.price - eps):
            self._book_fill(ts_ns, o, o.size, "through")
        elif abs(px - o.price) <= eps:
            eaten = min(sz, o.queue_ahead)
            o.queue_ahead -= eaten
            residual = sz - eaten
            if residual > 0.0:
                self._book_fill(ts_ns, o, min(residual, o.size), "sweep")
        self._sweep_dead()

    # ------------------------------------------------------------ ledger ---
    def ledger(self) -> dict[str, float]:
        """Recompute the decomposition from the blotter, in one late pass."""
        edge = fees = notional = 0.0
        for b in self.blotter:
            direction = self._signed(b.side)
            edge += direction * (b.mark_mid - b.price) * b.size
            fees += b.price * b.size * self.maker_fee_bps / 1e4
            notional += b.price * b.size
        return {
            "fills": float(len(self.blotter)),
            "edge_usd": edge,
            "inventory_usd": self._inventory_usd,
            "fees_usd": fees,
            "filled_notional_usd": notional,
            "net_usd": edge + self._inventory_usd - fees,
            "position": self._position,
        }


def replay_reference(
    events: list[Event],
    quote_size: float,
    cap_size: float | None,
    latency_ns: int,
    sz_decimals: int,
    queue_model: RefQueueModel = "own_level",
) -> ReferenceQuoteSim:
    """Feed an event list through the reference machine."""
    sim = ReferenceQuoteSim(
        quote_size=quote_size,
        cap_size=cap_size,
        latency_ns=latency_ns,
        sz_decimals=sz_decimals,
        queue_model=queue_model,
    )
    for ev in events:
        if ev[0] == "bbo":
            sim.bbo(ev[1], ev[2], ev[3], ev[4], ev[5])
        else:
            sim.trade(ev[1], ev[2], ev[3], ev[4])
    return sim
