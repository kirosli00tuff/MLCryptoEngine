"""Vendor cost gate: refuse past the cap, survive restarts, never guess.

Databento bills per request, so the gate is the only thing standing between
a mistyped date range and an unbounded charge. These tests pin the three
properties that make it trustworthy: it refuses when an estimate exceeds the
remaining budget, the cumulative total survives a process restart (many
small requests cannot walk past a cap none individually breaches), and an
unpriceable request is refused rather than assumed cheap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.config import AppConfig, BudgetSettings, load_config
from data.databento.budget import (
    BudgetExceededError,
    UnpriceableRequestError,
    check_affordable,
    commit,
    ledger_path,
    read_ledger,
    remaining_usd,
    spent_usd,
    summary,
)

DATE = "2026-07-31"


def _cfg(tmp_path: Path, cap: float = 25.0, refuse_without_estimate: bool = True) -> AppConfig:
    return AppConfig(
        data_root=tmp_path,
        logs_dir=tmp_path / "logs",
        venues=load_config().venues,
        budget=BudgetSettings(vendor_usd_cap=cap, refuse_without_estimate=refuse_without_estimate),
    )


def _commit(cfg: AppConfig, usd: float, symbol: str = "MES.c.0") -> None:
    commit(
        cfg,
        dataset="GLBX.MDP3",
        symbol=symbol,
        schema="mbp-10",
        date=DATE,
        usd=usd,
        billable_bytes=1_000,
    )


def test_gate_refuses_when_estimate_exceeds_remaining_budget(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, cap=5.0)
    _commit(cfg, 4.0)  # 1.00 left

    # Affordable: allowed, and reports the headroom that would remain.
    assert check_affordable(cfg, 0.25) == pytest.approx(0.75)

    with pytest.raises(BudgetExceededError, match="exceeds the remaining"):
        check_affordable(cfg, 1.01)
    # The refusal must name the numbers so the report is actionable.
    with pytest.raises(BudgetExceededError, match=r"\$1\.0000"):
        check_affordable(cfg, 2.0)
    # Refusing must not record a charge.
    assert spent_usd(cfg) == pytest.approx(4.0)
    assert len(read_ledger(cfg)) == 1


def test_many_small_requests_cannot_walk_past_the_cap(tmp_path: Path) -> None:
    """The failure a per-request-only check would miss."""
    cfg = _cfg(tmp_path, cap=1.0)
    for _ in range(10):
        check_affordable(cfg, 0.09)
        _commit(cfg, 0.09)
    assert spent_usd(cfg) == pytest.approx(0.9)

    # Each request is individually trivial; cumulatively they are at the cap.
    with pytest.raises(BudgetExceededError):
        check_affordable(cfg, 0.11)


def test_cumulative_total_survives_a_restart(tmp_path: Path) -> None:
    """The ledger is on disk, so a fresh process sees prior spend."""
    first = _cfg(tmp_path, cap=10.0)
    _commit(first, 9.5)

    # A brand-new config object over the same data root: nothing in memory.
    restarted = _cfg(tmp_path, cap=10.0)
    assert spent_usd(restarted) == pytest.approx(9.5)
    assert remaining_usd(restarted) == pytest.approx(0.5)
    with pytest.raises(BudgetExceededError):
        check_affordable(restarted, 0.6)
    assert ledger_path(restarted).is_file()


def test_unpriceable_request_is_refused_not_assumed_cheap(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    with pytest.raises(UnpriceableRequestError, match="never assumed cheap"):
        check_affordable(cfg, None)

    # Only an explicit opt-out permits it, and even then the cap still binds.
    permissive = _cfg(tmp_path, refuse_without_estimate=False)
    assert check_affordable(permissive, None) == pytest.approx(25.0)


def test_ledger_records_what_was_committed_and_summarises(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, cap=25.0)
    _commit(cfg, 2.5686, symbol="MES.c.0")
    _commit(cfg, 0.0652, symbol="MBT.c.0")

    entries = read_ledger(cfg)
    assert [e.symbol for e in entries] == ["MES.c.0", "MBT.c.0"]
    assert all(e.dataset == "GLBX.MDP3" and e.date == DATE for e in entries)
    assert summary(cfg) == {
        "cap_usd": 25.0,
        "spent_usd": 2.6338,
        "remaining_usd": 22.3662,
        "requests": 2,
    }


def test_negative_estimate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        check_affordable(_cfg(tmp_path), -1.0)
