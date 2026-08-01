"""Order book features: small pure functions over :class:`BookState`.

Every function returns ``None`` when its inputs are not available (empty or
invalid book side) — never a fabricated zero, so a missing book can never
masquerade as a balanced one.
"""

from __future__ import annotations

from research.stream.events import BookState


def ofi_best(prev: BookState, curr: BookState) -> float | None:
    """Best-level order flow imbalance contribution ``e_n``.

    Reference: Cont, Kukanov & Stoikov (2014), "The Price Impact of Order
    Book Events", eq. (10): bid-side depth additions at an improved-or-equal
    best bid count positive, ask-side additions at an improved-or-equal best
    ask count negative.
    """
    if (
        prev.best_bid is None
        or curr.best_bid is None
        or prev.best_ask is None
        or curr.best_ask is None
        or prev.bid_qty is None
        or curr.bid_qty is None
        or prev.ask_qty is None
        or curr.ask_qty is None
    ):
        return None
    contribution = 0.0
    if curr.best_bid >= prev.best_bid:
        contribution += curr.bid_qty
    if curr.best_bid <= prev.best_bid:
        contribution -= prev.bid_qty
    if curr.best_ask <= prev.best_ask:
        contribution -= curr.ask_qty
    if curr.best_ask >= prev.best_ask:
        contribution += prev.ask_qty
    return contribution


def ofi_deep(prev: BookState, curr: BookState, levels: int) -> float | None:
    """Aggregated depth-change imbalance across the top ``levels`` levels.

    Multi-level variant in the spirit of Cont-Kukanov-Stoikov: net change in
    visible bid depth minus net change in visible ask depth. Coarser than
    per-level flow decomposition but robust to level reshuffling.
    """
    if not (prev.bid_qtys and curr.bid_qtys and prev.ask_qtys and curr.ask_qtys):
        return None
    bid_change = sum(curr.bid_qtys[:levels]) - sum(prev.bid_qtys[:levels])
    ask_change = sum(curr.ask_qtys[:levels]) - sum(prev.ask_qtys[:levels])
    return bid_change - ask_change


def queue_imbalance(book: BookState) -> float | None:
    """(bid qty - ask qty) / (bid qty + ask qty) at the best level.

    Reference: Gould & Bonart (2016), "Queue imbalance as a one-tick-ahead
    price predictor".
    """
    if book.bid_qty is None or book.ask_qty is None:
        return None
    total = book.bid_qty + book.ask_qty
    if total <= 0:
        return None
    return (book.bid_qty - book.ask_qty) / total


def microprice_minus_mid(book: BookState) -> float | None:
    """Microprice minus mid: queue-weighted fair value shift.

    Reference: Stoikov (2018), "The micro-price: a high-frequency estimator
    of future prices". The microprice itself is computed by the Phase A
    replay; this feature is its displacement from the mid.
    """
    if book.microprice is None or book.mid is None:
        return None
    return book.microprice - book.mid


def spread(book: BookState) -> float | None:
    if book.best_bid is None or book.best_ask is None:
        return None
    return book.best_ask - book.best_bid


def spread_bps(book: BookState) -> float | None:
    value = spread(book)
    if value is None or book.mid is None or book.mid <= 0:
        return None
    return 1e4 * value / book.mid


def depth_at_levels(book: BookState, levels: int) -> tuple[list[float | None], list[float | None]]:
    """Visible qty at levels 1..``levels`` per side; None where the level is absent."""
    bids: list[float | None] = [
        book.bid_qtys[i] if i < len(book.bid_qtys) else None for i in range(levels)
    ]
    asks: list[float | None] = [
        book.ask_qtys[i] if i < len(book.ask_qtys) else None for i in range(levels)
    ]
    return bids, asks


def book_slope(book: BookState, levels: int) -> tuple[float | None, float | None]:
    """Cumulative depth per unit price distance, per side (qty / price unit).

    A steep slope means depth concentrated near the touch. Reference: Naes &
    Skjeltorp (2006), "Order book characteristics and the volume-volatility
    relation".
    """

    def side_slope(prices: tuple[float, ...], qtys: tuple[float, ...]) -> float | None:
        if len(prices) < 2 or len(qtys) < 2:
            return None
        span = abs(prices[min(levels, len(prices)) - 1] - prices[0])
        if span <= 0:
            return None
        return float(sum(qtys[:levels])) / span

    return side_slope(book.bid_prices, book.bid_qtys), side_slope(book.ask_prices, book.ask_qtys)


def book_asymmetry(book: BookState, levels: int) -> float | None:
    """(Σ bid depth - Σ ask depth) / (Σ bid depth + Σ ask depth), top ``levels``."""
    if not book.bid_qtys or not book.ask_qtys:
        return None
    bid_total = sum(book.bid_qtys[:levels])
    ask_total = sum(book.ask_qtys[:levels])
    total = bid_total + ask_total
    if total <= 0:
        return None
    return (bid_total - ask_total) / total


def depth_weighted_price_minus_mid(book: BookState, levels: int) -> float | None:
    """Depth-weighted price across both sides' top ``levels``, minus mid."""
    if not book.bid_prices or not book.ask_prices or book.mid is None:
        return None
    weighted = 0.0
    qty_total = 0.0
    for price, qty in zip(book.bid_prices[:levels], book.bid_qtys[:levels], strict=False):
        weighted += price * qty
        qty_total += qty
    for price, qty in zip(book.ask_prices[:levels], book.ask_qtys[:levels], strict=False):
        weighted += price * qty
        qty_total += qty
    if qty_total <= 0:
        return None
    return weighted / qty_total - book.mid
