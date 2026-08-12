"""Inventory under the declared D.1c quoting policy, from recorded fills.

The census measured spread minus adverse selection *per fill* and never
modelled the position held between fills. This simulator runs the registered
policy — two-sided quotes at the touch, fixed size, no skew, instant refill —
against the recorded aggressor prints, and decomposes the result exactly:

    mark-to-market PnL  =  spread edge  +  inventory term
    total net           =  edge + inventory + funding - fees

where the edge of a fill is its executed price against the contemporaneous
mid, and the inventory term is Σ position x Δmid between quotes. The identity
is asserted in tests, not assumed.

Fills are credited with the census's own optimism — every aggressor print
fills the opposite-side quote for ``min(print size, quote size)`` — so the
inventory term is measured under the same fill assumption the capture was.
An optional position cap refuses fills that would extend the position past
it and records the spread edge forgone, which is the real tradeoff a quoting
bot faces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAKER_FEE_BPS = 1.5
NS_PER_HOUR = 3_600_000_000_000
# |position notional| at or above the venue's $10 minimum order value counts
# as away from flat: below it the position could not even be quoted away.
FLAT_NOTIONAL_USD = 10.0


@dataclass
class InventorySim:
    """One instrument, one policy variant (uncapped or position-capped)."""

    symbol: str
    quote_size: float
    cap_size: float | None = None
    maker_fee_bps: float = MAKER_FEE_BPS

    position: float = 0.0
    cash_usd: float = 0.0
    edge_usd: float = 0.0
    inventory_usd: float = 0.0
    funding_usd: float = 0.0
    fees_usd: float = 0.0
    forgone_edge_usd: float = 0.0
    forgone_fills: int = 0
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

    _last_ns: int | None = None
    _last_mid: float | None = None
    _last_bid: float | None = None
    _last_ask: float | None = None

    def on_quote(self, ts_ns: int, bid: float, ask: float) -> None:
        """Advance the mark: credit held-position time and mark-to-market drift."""
        if bid <= 0.0 or ask <= 0.0 or ask <= bid:
            return
        mid = 0.5 * (bid + ask)
        if self._last_mid is not None:
            self._credit_time(ts_ns)
            drift = self.position * (mid - self._last_mid)
            self.inventory_usd += drift
            self._book(ts_ns, drift)
        self._last_ns, self._last_mid = ts_ns, mid
        self._last_bid, self._last_ask = bid, ask

    def _credit_time(self, ts_ns: int) -> None:
        """Credit elapsed time to the position held over it, at the last mark."""
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

    def on_trade(self, ts_ns: int, aggressor_sign: int, print_size: float) -> None:
        """An aggressor print fills the opposite-side quote at the touch.

        A buy aggressor (+1) lifts the ask, so the maker sells at the ask; a
        sell aggressor (-1) hits the bid, so the maker buys at the bid.
        """
        if self._last_mid is None or self._last_bid is None or self._last_ask is None:
            return
        self._credit_time(ts_ns)
        direction = -aggressor_sign
        exec_px = self._last_ask if direction < 0 else self._last_bid
        size = min(print_size, self.quote_size)
        if self.cap_size is not None:
            headroom = self.cap_size - direction * self.position
            allowed = max(0.0, min(size, headroom))
            refused = size - allowed
            if refused > 0.0:
                self.forgone_fills += 1
                self.forgone_edge_usd += abs(exec_px - self._last_mid) * refused
            size = allowed
        if size <= 0.0:
            return
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
        self._book(ts_ns, edge - fee)

    def on_funding(self, ts_ns: int, hourly_rate: float, mark: float) -> None:
        """Hourly funding on the held position: longs pay when the rate is positive."""
        self.funding_hours += 1
        charge = -self.position * mark * hourly_rate
        self.funding_usd += charge
        self._book(ts_ns, charge)

    def _book(self, ts_ns: int, delta_usd: float) -> None:
        """Add to the hourly net ledger and the running peak/drawdown track."""
        hour = ts_ns // NS_PER_HOUR
        self.net_by_hour[hour] = self.net_by_hour.get(hour, 0.0) + delta_usd
        net = self.total_net_usd()
        self.peak_net_usd = max(self.peak_net_usd, net)
        self.max_drawdown_usd = max(self.max_drawdown_usd, self.peak_net_usd - net)

    def mark_to_market_usd(self) -> float:
        """cash + position x mid — equals edge + inventory by construction."""
        return self.cash_usd + self.position * (self._last_mid or 0.0)

    def total_net_usd(self) -> float:
        return self.edge_usd + self.inventory_usd + self.funding_usd - self.fees_usd

    def worst_hour(self) -> tuple[int, float] | None:
        if not self.net_by_hour:
            return None
        hour = min(self.net_by_hour, key=lambda h: self.net_by_hour[h])
        return hour, self.net_by_hour[hour]

    def summary(self) -> dict[str, Any]:
        def per_notional_bps(usd: float) -> float | None:
            return usd / self.filled_notional_usd * 1e4 if self.filled_notional_usd else None

        worst = self.worst_hour()
        net = self.total_net_usd()
        return {
            "symbol": self.symbol,
            "quote_size": self.quote_size,
            "cap_size": self.cap_size,
            "fills": self.fills,
            "filled_notional_usd": self.filled_notional_usd,
            "final_position": self.position,
            "max_abs_position": self.max_abs_position,
            "time_hours": self.total_ns / NS_PER_HOUR,
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
            "edge_bps": per_notional_bps(self.edge_usd),
            "inventory_bps": per_notional_bps(self.inventory_usd),
            "funding_bps": per_notional_bps(self.funding_usd),
            "fees_bps": per_notional_bps(self.fees_usd),
            "net_bps": per_notional_bps(net),
            "forgone_edge_usd": self.forgone_edge_usd,
            "forgone_fills": self.forgone_fills,
            "max_drawdown_usd": self.max_drawdown_usd,
            "worst_hour_utc": worst[0] if worst else None,
            "worst_hour_usd": worst[1] if worst else None,
            "net_without_worst_hour_usd": net - worst[1] if worst else None,
            "funding_hours": self.funding_hours,
        }
