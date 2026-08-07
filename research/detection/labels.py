"""Four-class detection labels from keyless sources, C.19's recommendation built.

One label per mechanism, never a binary: **hard_rug** from SolRPDS liquidity
aggregates (≥ 99% of added liquidity later removed); **honeypot** from GoPlus
token-extension state; **soft_rug** and **slow_rug** are *not labelable* from
keyless sources and live in an explicit ``unlabeled_residual`` rather than
being folded into a class they do not belong to. The RugCheck ``rugged`` flag
is discarded entirely — it recovered zero of four documented rugs in C.19.

The honest minority is identified as **honest_candidate** — not hard-rug and
still Active — and is an *upper bound* on honesty: soft and slow rugs
contaminate it from above, which is exactly why it is named candidate.

The monotonic-authority inference (ADR-045) lives here as code: a mint or
freeze authority can be revoked but never restored, so **present-now proves
present-at-launch** — a leak-free pre-event inference — while absent-now
proves nothing about when it went.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

HARD_RUG_REMOVAL_FRACTION = 0.99
HONEST_CANDIDATE = "honest_candidate"
HARD_RUG = "hard_rug"
UNLABELED_RESIDUAL = "unlabeled_residual"
# GoPlus fields whose truthiness marks the honeypot mechanism. transfer_fee and
# default_account_state are provenance-classified but not flag-worthy alone.
HONEYPOT_FIELDS = ("freezable", "non_transferable", "transfer_hook")


@dataclass(frozen=True)
class PoolRecord:
    """One SolRPDS pool row, parsed and typed."""

    mint: str
    added: float
    removed: float
    first_ts: datetime | None
    last_ts: datetime | None
    status: str

    @property
    def lifetime_seconds(self) -> float | None:
        """First pool activity to last pool activity — the removal proxy.

        SolRPDS carries no explicit removal timestamp; for hard-rug pools the
        final pool operation is the remove, so last activity bounds it. 96.8%
        of hard-rug pools show token swaps *after* last pool activity, which is
        consistent with the proxy (swaps trail on the dead pair) rather than
        contradicting it.
        """
        if self.first_ts is None or self.last_ts is None or self.last_ts < self.first_ts:
            return None
        return (self.last_ts - self.first_ts).total_seconds()


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_row(row: dict[str, str]) -> PoolRecord:
    def num(key: str) -> float:
        try:
            return float(row.get(key) or 0.0)
        except ValueError:
            return 0.0

    return PoolRecord(
        mint=(row.get("MINT") or "").strip(),
        added=num("TOTAL_ADDED_LIQUIDITY"),
        removed=num("TOTAL_REMOVED_LIQUIDITY"),
        first_ts=_ts(row.get("FIRST_POOL_ACTIVITY_TIMESTAMP")),
        last_ts=_ts(row.get("LAST_POOL_ACTIVITY_TIMESTAMP")),
        status=(row.get("INACTIVITY_STATUS") or "").strip(),
    )


def is_hard_rug(added: float, removed: float) -> bool:
    """≥ 99% of added liquidity later removed, with liquidity ever added."""
    return added > 0.0 and removed >= HARD_RUG_REMOVAL_FRACTION * added


def classify(record: PoolRecord) -> str:
    """Mechanism class for one pool. Honeypot rides on the mint, not the pool."""
    if is_hard_rug(record.added, record.removed):
        return HARD_RUG
    if record.status == "Active":
        return HONEST_CANDIDATE
    return UNLABELED_RESIDUAL


def _truthy(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("status") in ("1", 1) or bool(value.get("authority"))
    return value in ("1", 1, True)


def honeypot_from_goplus(entry: dict[str, Any] | None) -> bool | None:
    """Honeypot label from GoPlus token security, ``None`` when unresolved.

    Unresolved is not False: GoPlus coverage skews against old dead mints —
    the positive class — so collapsing missing to benign would bias exactly
    the way this track cannot afford.
    """
    if not entry:
        return None
    return any(_truthy(entry.get(field)) for field in HONEYPOT_FIELDS)


def authority_pre_event(present_now: bool | None) -> str:
    """The monotonic inference, one direction only (ADR-045).

    Authorities are revocable, never restorable. Present now therefore proves
    present at launch — a leak-free pre-event fact. Absent now proves nothing
    about when it went, and unknown stays unknown.
    """
    if present_now is True:
        return "pre_event_present"
    return "indeterminate"


def baselines(n_honest: int, n_total: int) -> dict[str, dict[str, float | None]]:
    """Trivial baselines on the minority (honest) class, from the actual counts.

    The always-rug classifier predicts no honest tokens: its honest-class
    precision is undefined (0/0) and reported as ``None``, never as 0 or 1.
    """
    rate = n_honest / n_total if n_total else 0.0
    return {
        "always_rug": {"honest_precision": None, "honest_recall": 0.0},
        "always_honest": {"honest_precision": rate, "honest_recall": 1.0},
        "random_at_base_rate": {"honest_precision": rate, "honest_recall": rate},
    }
