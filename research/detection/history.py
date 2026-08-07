"""Launch-window reconstruction: pre-event features and decontamination rules.

Everything here is a pure function over transaction records so the leakage
suite could be wired **before the first real feature is ever computed** — the
Task 4 ordering, honoured literally: these functions ship tested against
synthetic histories while the indexer key does not yet exist.

**The window: 1,800 seconds from first pool activity.** Justification, not
taste: C.20 measured hard-rug lifetimes at Q25 = 2.6 h and median = 2.55 d,
so a 30-minute window sits strictly before the label event for roughly nine
in ten hard rugs while remaining short enough to matter for avoidance — the
tool's decision point is "score at T0+30 min and act". Pools whose label
event falls **inside** the window are not clamped, not truncated, and not
quietly included: :func:`feature_window_end` refuses them with
:class:`WindowLeakError`, the caller counts them as excluded, and that count
is reported. A window extending past the label event is a leak regardless of
how the feature is named.

Decontamination (Task 3), rules fixed before any data: within the insider set
(creator plus wallets whose first funding came from the creator), selling
**≥ 70% of window-end holdings within 72 h** of T0 is a **soft rug**; reaching
70% only later but **within 30 days** is a **slow rug**; otherwise the pool
stays honest_candidate. Both thresholds are registered here, dated, and move
only by ADR.
"""

from __future__ import annotations

from dataclasses import dataclass

WINDOW_SECONDS = 1_800.0
SOFT_RUG_HORIZON_S = 72 * 3_600.0
SLOW_RUG_HORIZON_S = 30 * 86_400.0
INSIDER_SELL_FRACTION = 0.70
TOP_N = 5


class WindowLeakError(RuntimeError):
    """The label event falls inside the feature window: computation refused."""


@dataclass(frozen=True)
class Tx:
    """One parsed transaction touching the token."""

    ts_s: float
    kind: str  # mint_to | transfer | sell | revoke_authority
    wallet: str
    amount: float = 0.0
    source: str = ""  # funding counterparty for transfers


def feature_window_end(t0_s: float, label_event_s: float | None) -> float:
    """T0 + 30 min, or a refusal if the label event sits inside the window."""
    end = t0_s + WINDOW_SECONDS
    if label_event_s is not None and label_event_s <= end:
        raise WindowLeakError(
            f"label event at {label_event_s:.0f}s is inside the feature window ending "
            f"{end:.0f}s; the pool is EXCLUDED from the modeled set, never clamped in"
        )
    return end


def balances_at(txs: list[Tx], cutoff_s: float) -> dict[str, float]:
    """Holdings replayed from history up to ``cutoff_s`` inclusive.

    Reads nothing after the cutoff — prefix invariance holds by construction
    and is held down by test, not by trust.
    """
    out: dict[str, float] = {}
    for tx in txs:
        if tx.ts_s > cutoff_s:
            continue
        if tx.kind == "mint_to":
            out[tx.wallet] = out.get(tx.wallet, 0.0) + tx.amount
        elif tx.kind == "transfer":
            out[tx.source] = out.get(tx.source, 0.0) - tx.amount
            out[tx.wallet] = out.get(tx.wallet, 0.0) + tx.amount
        elif tx.kind == "sell":
            out[tx.wallet] = out.get(tx.wallet, 0.0) - tx.amount
    return {w: b for w, b in out.items() if b > 1e-12}


def insider_set(txs: list[Tx], creator: str, cutoff_s: float) -> set[str]:
    """Creator plus wallets whose FIRST inbound funding came from the creator."""
    first_source: dict[str, str] = {}
    for tx in sorted(txs, key=lambda t: t.ts_s):
        if tx.ts_s > cutoff_s or tx.kind != "transfer":
            continue
        first_source.setdefault(tx.wallet, tx.source)
    return {creator} | {w for w, s in first_source.items() if s == creator}


def features(
    txs: list[Tx], t0_s: float, creator: str, label_event_s: float | None
) -> dict[str, float | None]:
    """The indexer feature set, every value read strictly inside the window."""
    end = feature_window_end(t0_s, label_event_s)
    at_t0 = balances_at(txs, t0_s)
    at_end = balances_at(txs, end)
    total_end = sum(at_end.values())
    top5 = sum(sorted(at_end.values(), reverse=True)[:TOP_N]) / total_end if total_end else None
    first_sell = min(
        (tx.ts_s for tx in txs if tx.kind == "sell" and tx.wallet == creator and tx.ts_s <= end),
        default=None,
    )
    revoked = min(
        (tx.ts_s for tx in txs if tx.kind == "revoke_authority" and tx.ts_s <= end),
        default=None,
    )
    insiders = insider_set(txs, creator, end)
    return {
        "creator_allocation_t0": (at_t0.get(creator, 0.0) / sum(at_t0.values())) if at_t0 else None,
        "top5_concentration_wend": top5,
        "creator_time_to_first_sell_s": (first_sell - t0_s) if first_sell is not None else None,
        "authority_revoked_in_window": float(revoked is not None),
        "n_early_holders": float(len(at_end)),
        "insider_funded_early_holders": float(len(insiders - {creator})),
    }


def decontaminate(txs: list[Tx], t0_s: float, creator: str) -> str:
    """soft_rug / slow_rug / honest_candidate from insider sell behaviour."""
    end = t0_s + WINDOW_SECONDS
    insiders = insider_set(txs, creator, end)
    held = sum(balances_at(txs, end).get(w, 0.0) for w in insiders)
    if held <= 0:
        return "honest_candidate"

    def sold_by(horizon_s: float) -> float:
        return sum(
            tx.amount
            for tx in txs
            if tx.kind == "sell" and tx.wallet in insiders and end < tx.ts_s <= t0_s + horizon_s
        )

    if sold_by(SOFT_RUG_HORIZON_S) >= INSIDER_SELL_FRACTION * held:
        return "soft_rug"
    if sold_by(SLOW_RUG_HORIZON_S) >= INSIDER_SELL_FRACTION * held:
        return "slow_rug"
    return "honest_candidate"
