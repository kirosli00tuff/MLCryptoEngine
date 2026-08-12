"""The D.1d bounded fill replay: a resting quote under queue, latency, and ALO.

D.1c's :class:`~research.microstructure.inventory.InventorySim` credited every
print with ``min(print, quote)`` at the touch — generous on fills, which is
what made it the right instrument for isolating the inventory term. This
engine tightens fills to what a resting order would experience, per the
policy registered in report.md §D.1d:

- **Queue** at the always-last bound (D.1a: the only defensible model). An
  order at price p fills only on level-exhaustion evidence: a full-sweep
  print at p (size ≥ the visible touch), a print strictly through p, or the
  opposing touch crossing p on a bbo update (the stale-price fill while a
  cancel is in flight).
- **Latency** in both directions: placements become active one L after they
  are issued, cancels take effect one L after they are issued, and the order
  stays fillable at its stale price until the cancel lands — the leg where
  latency costs money.
- **ALO**: an order that would cross on arrival is rejected, counted, and
  retried at the next bbo update.

State transitions are evaluated against the last observed touch — the same
resolution C.27 and D.1a used; the bbo cadence (~123-330 ms median) is the
clock this feed can support.

The PnL ledger deliberately mirrors ``InventorySim`` field-for-field rather
than sharing code with it: the Task 2 known-answer gate runs this engine in
``generous`` mode against ``InventorySim`` on identical events, and that
check is only independent if the two ledgers are separate implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from research.microstructure.tick import tick_size

MAKER_FEE_BPS = 1.5
NS_PER_HOUR = 3_600_000_000_000
FLAT_NOTIONAL_USD = 10.0

FillModel = Literal["always_last", "improved", "generous"]
_SIDES = ("bid", "ask")
_DIRECTION = {"bid": 1, "ask": -1}


@dataclass
class _Order:
    price: float
    size: float
    active_ns: int
    cancel_dead_ns: int | None = None
    alo_checked: bool = False
    expected_edge_bps: float = 0.0

    def is_live(self, ts_ns: int) -> bool:
        return self.active_ns <= ts_ns


@dataclass
class BoundedQuoteSim:
    """One instrument, one policy variant, one fill model."""

    symbol: str
    quote_size: float
    cap_size: float | None
    latency_ns: int
    sz_decimals: int
    fill_model: FillModel = "always_last"
    maker_fee_bps: float = MAKER_FEE_BPS

    # Ledger — field-for-field the InventorySim decomposition.
    position: float = 0.0
    cash_usd: float = 0.0
    edge_usd: float = 0.0
    inventory_usd: float = 0.0
    funding_usd: float = 0.0
    fees_usd: float = 0.0
    fills: int = 0
    filled_notional_usd: float = 0.0
    funding_hours: int = 0
    max_abs_position: float = 0.0
    total_ns: int = 0
    nonflat_ns: int = 0
    at_cap_ns: int = 0
    sum_abs_notional_ns: float = 0.0
    peak_net_usd: float = 0.0
    max_drawdown_usd: float = 0.0
    net_by_hour: dict[int, float] = field(default_factory=dict)
    fees_by_hour: dict[int, float] = field(default_factory=dict)

    # Replay-specific measured outputs.
    placements: int = 0
    alo_rejections: int = 0
    cancels_started: int = 0
    fills_sweep: int = 0
    fills_through: int = 0
    fills_crossing: int = 0
    trade_records: list[tuple[int, str, float, float, float, float]] = field(default_factory=list)
    sum_expected_edge_bps_notional: float = 0.0
    edge_usd_by_reason: dict[str, float] = field(default_factory=dict)
    notional_by_reason: dict[str, float] = field(default_factory=dict)

    _orders: dict[str, _Order | None] = field(default_factory=lambda: dict.fromkeys(_SIDES))
    _rejected_this_update: dict[str, bool] = field(
        default_factory=lambda: dict.fromkeys(_SIDES, False)
    )
    _bid_px: float | None = None
    _bid_sz: float = 0.0
    _ask_px: float | None = None
    _ask_sz: float = 0.0
    _last_ns: int | None = None
    _last_mid: float | None = None

    # ------------------------------------------------------------- events --
    def on_bbo(
        self, ts_ns: int, bid_px: float, bid_sz: float, ask_px: float, ask_sz: float
    ) -> None:
        if bid_px <= 0.0 or ask_px <= 0.0 or ask_px <= bid_px:
            return
        mid = 0.5 * (bid_px + ask_px)
        if self._last_mid is not None:
            self._credit_time(ts_ns)
            drift = self.position * (mid - self._last_mid)
            self.inventory_usd += drift
            self._book(ts_ns, drift, fee=0.0)
        self._last_ns, self._last_mid = ts_ns, mid

        if self.fill_model != "generous":
            self._process_transitions(ts_ns, bid_px, ask_px)
            self._crossing_fills(ts_ns, bid_px, ask_px)
            self._cancel_stale(ts_ns, bid_px, ask_px)
            self._place_wanted(ts_ns, bid_px, ask_px, mid)
            for side in _SIDES:
                self._rejected_this_update[side] = False

        self._bid_px, self._bid_sz = bid_px, bid_sz
        self._ask_px, self._ask_sz = ask_px, ask_sz

    def on_trade(self, ts_ns: int, aggressor_sign: int, px: float, sz: float) -> None:
        if self._last_mid is None:
            return
        self._credit_time(ts_ns)
        if self.fill_model == "generous":
            self._generous_fill(ts_ns, aggressor_sign, sz)
            return
        if self._bid_px is None or self._ask_px is None:
            return
        self._process_transitions(ts_ns, self._bid_px, self._ask_px)
        side = "ask" if aggressor_sign > 0 else "bid"
        order = self._orders[side]
        if order is None or not order.is_live(ts_ns):
            return
        eps = 0.5 * tick_size(self._last_mid, self.sz_decimals)
        if self.fill_model == "improved":
            reached = px >= order.price - eps if side == "ask" else px <= order.price + eps
            if reached:
                self._fill(ts_ns, side, order, min(sz, order.size), "sweep")
            return
        through = px > order.price + eps if side == "ask" else px < order.price - eps
        at_price = abs(px - order.price) <= eps
        visible = self._ask_sz if side == "ask" else self._bid_sz
        if through:
            self._fill(ts_ns, side, order, order.size, "through")
        elif at_price and sz >= visible > 0.0:
            self._fill(ts_ns, side, order, min(sz, order.size), "sweep")

    def on_funding(self, ts_ns: int, hourly_rate: float, mark: float) -> None:
        self.funding_hours += 1
        charge = -self.position * mark * hourly_rate
        self.funding_usd += charge
        self._book(ts_ns, charge, fee=0.0)

    # ------------------------------------------------------ order machine --
    def _process_transitions(self, ts_ns: int, bid_px: float, ask_px: float) -> None:
        """Bury dead cancels; run the one-shot ALO check on newly arrived orders."""
        for side in _SIDES:
            order = self._orders[side]
            if order is None:
                continue
            if order.cancel_dead_ns is not None and order.cancel_dead_ns <= ts_ns:
                self._orders[side] = None
                continue
            if order.is_live(ts_ns) and not order.alo_checked:
                order.alo_checked = True
                crosses = order.price >= ask_px if side == "bid" else order.price <= bid_px
                if crosses:
                    # The venue rejects an ALO that would match, never reprices.
                    self.alo_rejections += 1
                    self._orders[side] = None
                    self._rejected_this_update[side] = True

    def _crossing_fills(self, ts_ns: int, bid_px: float, ask_px: float) -> None:
        """The opposing touch crossed a live order's price: stale-price fill."""
        for side in _SIDES:
            order = self._orders[side]
            if order is None or not order.is_live(ts_ns):
                continue
            crossed = bid_px >= order.price if side == "ask" else ask_px <= order.price
            if crossed:
                self._fill(ts_ns, side, order, order.size, "crossing")

    def _cancel_stale(self, ts_ns: int, bid_px: float, ask_px: float) -> None:
        """Touch left our price (or cap withdrawal): start a latency-bound cancel."""
        for side in _SIDES:
            order = self._orders[side]
            if order is None or not order.is_live(ts_ns) or order.cancel_dead_ns is not None:
                continue
            target = self._target_price(side, bid_px, ask_px)
            if order.price != target or self._side_capped(side):
                order.cancel_dead_ns = ts_ns + self.latency_ns
                self.cancels_started += 1

    def _place_wanted(self, ts_ns: int, bid_px: float, ask_px: float, mid: float) -> None:
        for side in _SIDES:
            if (
                self._orders[side] is not None
                or self._rejected_this_update[side]
                or self._side_capped(side)
            ):
                continue
            spread_bps = (ask_px - bid_px) / mid * 1e4
            expected = spread_bps / 2.0
            if self.fill_model == "improved":
                expected -= tick_size(mid, self.sz_decimals) / mid * 1e4
            self._orders[side] = _Order(
                price=self._target_price(side, bid_px, ask_px),
                size=self.quote_size,
                active_ns=ts_ns + self.latency_ns,
                expected_edge_bps=expected,
            )
            self.placements += 1

    def _target_price(self, side: str, bid_px: float, ask_px: float) -> float:
        if self.fill_model != "improved":
            return bid_px if side == "bid" else ask_px
        tick = tick_size(0.5 * (bid_px + ask_px), self.sz_decimals)
        return bid_px + tick if side == "bid" else ask_px - tick

    def _side_capped(self, side: str) -> bool:
        if self.cap_size is None:
            return False
        return _DIRECTION[side] * self.position >= self.cap_size

    # ------------------------------------------------------------- fills ---
    def _fill(self, ts_ns: int, side: str, order: _Order, size: float, reason: str) -> None:
        direction = _DIRECTION[side]
        if self.cap_size is not None:
            headroom = self.cap_size - direction * self.position
            size = min(size, max(0.0, headroom))
        if size <= 0.0 or self._last_mid is None:
            self._orders[side] = None
            return
        exec_px = order.price
        self._settle(ts_ns, direction, exec_px, size)
        self.trade_records.append(
            (
                ts_ns,
                "long" if direction > 0 else "short",
                size,
                exec_px,
                direction * (self._last_mid - exec_px) * size,
                exec_px * size * self.maker_fee_bps / 1e4,
            )
        )
        self.sum_expected_edge_bps_notional += order.expected_edge_bps * exec_px * size
        if reason == "sweep":
            self.fills_sweep += 1
        elif reason == "through":
            self.fills_through += 1
        else:
            self.fills_crossing += 1
        # Which fill rule the edge came from. Purely diagnostic — it changes no
        # total — but a closure resting on a pessimistic rule should have to say
        # how much of itself that rule accounts for.
        self.edge_usd_by_reason[reason] = self.edge_usd_by_reason.get(reason, 0.0) + (
            direction * (self._last_mid - exec_px) * size
        )
        self.notional_by_reason[reason] = self.notional_by_reason.get(reason, 0.0) + exec_px * size
        self._orders[side] = None

    def _generous_fill(self, ts_ns: int, aggressor_sign: int, print_size: float) -> None:
        if self._bid_px is None or self._ask_px is None:
            return
        direction = -aggressor_sign
        exec_px = self._ask_px if direction < 0 else self._bid_px
        size = min(print_size, self.quote_size)
        if self.cap_size is not None:
            headroom = self.cap_size - direction * self.position
            size = min(size, max(0.0, headroom))
        if size > 0.0:
            self._settle(ts_ns, direction, exec_px, size)

    def _settle(self, ts_ns: int, direction: int, exec_px: float, size: float) -> None:
        assert self._last_mid is not None
        self.fills += 1
        notional = exec_px * size
        self.filled_notional_usd += notional
        self.position += direction * size
        self.cash_usd -= direction * notional
        self.max_abs_position = max(self.max_abs_position, abs(self.position))
        edge = direction * (self._last_mid - exec_px) * size
        fee = notional * self.maker_fee_bps / 1e4
        self.edge_usd += edge
        self.fees_usd += fee
        self._book(ts_ns, edge - fee, fee=fee)

    # ------------------------------------------------------------ ledger ---
    def _credit_time(self, ts_ns: int) -> None:
        if self._last_ns is None or self._last_mid is None:
            return
        dt = ts_ns - self._last_ns
        if dt > 0:
            self.total_ns += dt
            notional = abs(self.position) * self._last_mid
            self.sum_abs_notional_ns += notional * dt
            if notional >= FLAT_NOTIONAL_USD:
                self.nonflat_ns += dt
            if self.cap_size is not None and abs(self.position) >= self.cap_size:
                self.at_cap_ns += dt
        self._last_ns = ts_ns

    def _book(self, ts_ns: int, delta_usd: float, fee: float) -> None:
        hour = ts_ns // NS_PER_HOUR
        self.net_by_hour[hour] = self.net_by_hour.get(hour, 0.0) + delta_usd
        if fee:
            self.fees_by_hour[hour] = self.fees_by_hour.get(hour, 0.0) + fee
        net = self.total_net_usd()
        self.peak_net_usd = max(self.peak_net_usd, net)
        self.max_drawdown_usd = max(self.max_drawdown_usd, self.peak_net_usd - net)

    def mark_to_market_usd(self) -> float:
        return self.cash_usd + self.position * (self._last_mid or 0.0)

    def total_net_usd(self) -> float:
        return self.edge_usd + self.inventory_usd + self.funding_usd - self.fees_usd

    def summary(self) -> dict[str, Any]:
        def bps(usd: float) -> float | None:
            return usd / self.filled_notional_usd * 1e4 if self.filled_notional_usd else None

        net = self.total_net_usd()
        return {
            "symbol": self.symbol,
            "fill_model": self.fill_model,
            "quote_size": self.quote_size,
            "cap_size": self.cap_size,
            "latency_ms": self.latency_ns / 1e6,
            "fills": self.fills,
            "fills_sweep": self.fills_sweep,
            "fills_through": self.fills_through,
            "fills_crossing": self.fills_crossing,
            "placements": self.placements,
            "alo_rejections": self.alo_rejections,
            "alo_rejection_rate": (
                self.alo_rejections / (self.placements + self.alo_rejections)
                if self.placements + self.alo_rejections
                else None
            ),
            "cancels_started": self.cancels_started,
            "filled_notional_usd": self.filled_notional_usd,
            "final_position": self.position,
            "max_abs_position": self.max_abs_position,
            "frac_time_away_from_flat": (
                self.nonflat_ns / self.total_ns if self.total_ns else None
            ),
            "frac_time_at_cap": (self.at_cap_ns / self.total_ns if self.total_ns else None),
            "mean_abs_notional_usd": (
                self.sum_abs_notional_ns / self.total_ns if self.total_ns else None
            ),
            "edge_usd": self.edge_usd,
            "inventory_usd": self.inventory_usd,
            "funding_usd": self.funding_usd,
            "fees_usd": self.fees_usd,
            "net_usd": net,
            "edge_bps": bps(self.edge_usd),
            "inventory_bps": bps(self.inventory_usd),
            "funding_bps": bps(self.funding_usd),
            "fees_bps": bps(self.fees_usd),
            "net_bps": bps(net),
            "expected_edge_bps": (
                self.sum_expected_edge_bps_notional / self.filled_notional_usd
                if self.filled_notional_usd
                else None
            ),
            "edge_usd_by_reason": dict(self.edge_usd_by_reason),
            "edge_bps_by_reason": {
                reason: usd / self.notional_by_reason[reason] * 1e4
                for reason, usd in self.edge_usd_by_reason.items()
                if self.notional_by_reason.get(reason)
            },
            "notional_by_reason": dict(self.notional_by_reason),
            "max_drawdown_usd": self.max_drawdown_usd,
            "funding_hours": self.funding_hours,
        }
