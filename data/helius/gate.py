"""The Helius credit gate: refuse first, spend second, ledger everything.

Pricing method, stated because the registration demands it: Helius exposes no
usage endpoint reachable without a key (and none was found documented for the
free tier), so cost is **derived from request counts against a weighted
schedule** rather than read from an API. The weights below are conservative
placeholders dated 2026-08-06 and are **unverified against the dashboard** —
the ledger records raw request counts precisely so the operator can reconcile
real credit burn against it and correct the weights with one edit.

The Databento cost gate refused two purchases correctly (ADR-017); this gate
inherits its shape: a cumulative on-disk ledger (append-only, so the cap
survives a restart), a hard cap from config, and a refusal that names the
arithmetic instead of proceeding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson

from data.config import AppConfig

LEDGER_NAME = "helius_credit_ledger.jsonl"
# Request-weighted credits, 2026-08-06, UNVERIFIED against the dashboard:
# plain RPC calls are cheap, Enhanced/parsed-history calls are not. Reconcile
# and correct via the ledger's raw counts; never loosen mid-sweep.
CREDIT_WEIGHTS: dict[str, int] = {"rpc": 1, "enhanced": 10}


class CreditCapError(RuntimeError):
    """A request (or sweep estimate) would breach the registered credit cap."""


@dataclass(frozen=True)
class Charge:
    ts: str
    kind: str
    n: int
    weighted: int
    cumulative: int
    note: str


class CreditGate:
    """Hard credit ceiling enforced against an append-only on-disk ledger."""

    def __init__(self, cfg: AppConfig, ledger_path: Path | None = None) -> None:
        self.cap = int(cfg.helius_credit_cap)
        self.path = ledger_path or (cfg.data_root / "vendor" / LEDGER_NAME)

    def spent(self) -> int:
        """Cumulative weighted credits, re-read from disk so restarts count."""
        if not self.path.is_file():
            return 0
        total = 0
        with self.path.open("rb") as fh:
            for line in fh:
                if line.strip():
                    total += int(orjson.loads(line)["weighted"])
        return total

    def remaining(self) -> int:
        return max(0, self.cap - self.spent())

    def estimate(self, n_requests: int, kind: str) -> int:
        return n_requests * CREDIT_WEIGHTS[kind]

    def check_estimate(self, weighted: int, what: str) -> None:
        """Refuse a planned sweep before its first request, by arithmetic."""
        spent = self.spent()
        if spent + weighted > self.cap:
            raise CreditCapError(
                f"REFUSED {what}: estimated {weighted} weighted credits + {spent} already "
                f"spent exceeds the cap of {self.cap} (ADR-046). Nothing was sent. Shrink "
                "the sweep or raise helius_credit_cap by operator edit."
            )

    def charge(self, kind: str, n_requests: int = 1, note: str = "") -> Charge:
        """Charge BEFORE the request: a refusal must leave the ledger unchanged."""
        weighted = self.estimate(n_requests, kind)
        self.check_estimate(weighted, note or f"{n_requests}x {kind}")
        entry = Charge(
            ts=datetime.now(UTC).isoformat(),
            kind=kind,
            n=n_requests,
            weighted=weighted,
            cumulative=self.spent() + weighted,
            note=note,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as fh:
            fh.write(orjson.dumps(entry.__dict__) + b"\n")
        return entry
