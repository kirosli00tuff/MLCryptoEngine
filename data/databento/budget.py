"""Cost gate for metered vendor data: price every request, refuse past the cap.

Databento bills per request, so a mistyped date range or a schema swap can
turn a cent into a hundred dollars with no warning from the client. Three
properties make the gate trustworthy:

1. **Every request is priced before it is issued.** The estimate comes from
   the vendor's own metadata endpoints, which cost nothing to call.
2. **The cap is cumulative and on disk.** A per-request check alone would
   let a hundred small requests walk past a cap none of them individually
   breached. The ledger at ``data/vendor/spend_ledger.jsonl`` is append-only
   and survives restarts, so the ceiling is a real ceiling rather than a
   per-process convention.
3. **Unpriceable means refused.** If an estimate cannot be obtained the gate
   closes (``refuse_without_estimate``); a request with unknown cost is
   never assumed cheap.

The ledger records what was *committed* before each download. Recording
after the fact would leave a crash window in which money was spent and the
ledger did not know it — the ledger must be pessimistic, never optimistic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from data.config import AppConfig

LEDGER_NAME = "spend_ledger.jsonl"


class BudgetExceededError(RuntimeError):
    """A priced request would push cumulative spend past the configured cap."""


class UnpriceableRequestError(RuntimeError):
    """No cost estimate could be obtained, and the gate refuses to guess."""


@dataclass(frozen=True, slots=True)
class SpendEntry:
    """One committed vendor charge."""

    ts: str
    dataset: str
    symbol: str
    schema: str
    date: str
    usd: float
    billable_bytes: int
    note: str = ""


def ledger_path(cfg: AppConfig) -> Path:
    return cfg.data_root / "vendor" / LEDGER_NAME


def read_ledger(cfg: AppConfig) -> list[SpendEntry]:
    """Every committed charge, oldest first. Missing ledger means no spend."""
    path = ledger_path(cfg)
    if not path.is_file():
        return []
    entries: list[SpendEntry] = []
    with path.open("rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                entries.append(SpendEntry(**orjson.loads(stripped)))
    return entries


def spent_usd(cfg: AppConfig) -> float:
    return sum(entry.usd for entry in read_ledger(cfg))


def remaining_usd(cfg: AppConfig) -> float:
    return cfg.budget.vendor_usd_cap - spent_usd(cfg)


def _append(cfg: AppConfig, entry: SpendEntry) -> None:
    path = ledger_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        fh.write(orjson.dumps(asdict(entry)) + b"\n")


def check_affordable(cfg: AppConfig, estimate_usd: float | None) -> float:
    """Raise unless ``estimate_usd`` fits inside the remaining budget.

    Returns the budget that would remain after committing, so callers can
    report headroom. Refuses a ``None`` estimate when
    ``refuse_without_estimate`` is set — the default and the safe reading.
    """
    if estimate_usd is None:
        if cfg.budget.refuse_without_estimate:
            raise UnpriceableRequestError(
                "no cost estimate available for this request and "
                "budget.refuse_without_estimate is set: an unpriced request is "
                "never assumed cheap. Price it via the vendor metadata API first."
            )
        return remaining_usd(cfg)
    if estimate_usd < 0:
        raise ValueError(f"negative cost estimate {estimate_usd}")
    remaining = remaining_usd(cfg)
    if estimate_usd > remaining:
        raise BudgetExceededError(
            f"request estimated at ${estimate_usd:.4f} exceeds the remaining "
            f"vendor budget of ${remaining:.4f} "
            f"(cap ${cfg.budget.vendor_usd_cap:.2f}, already committed "
            f"${spent_usd(cfg):.4f}). Refusing to issue it. Raise "
            "budget.vendor_usd_cap in config/default.yaml only as a deliberate "
            "decision."
        )
    return remaining - estimate_usd


def commit(
    cfg: AppConfig,
    *,
    dataset: str,
    symbol: str,
    schema: str,
    date: str,
    usd: float,
    billable_bytes: int,
    note: str = "",
) -> SpendEntry:
    """Record a charge *before* issuing the request the charge pays for."""
    entry = SpendEntry(
        ts=datetime.now(UTC).isoformat(),
        dataset=dataset,
        symbol=symbol,
        schema=schema,
        date=date,
        usd=usd,
        billable_bytes=billable_bytes,
        note=note,
    )
    _append(cfg, entry)
    return entry


def summary(cfg: AppConfig) -> dict[str, Any]:
    entries = read_ledger(cfg)
    spent = sum(e.usd for e in entries)
    return {
        "cap_usd": cfg.budget.vendor_usd_cap,
        "spent_usd": round(spent, 4),
        "remaining_usd": round(cfg.budget.vendor_usd_cap - spent, 4),
        "requests": len(entries),
    }
