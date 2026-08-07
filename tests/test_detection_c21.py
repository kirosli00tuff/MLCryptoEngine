"""C.21 tests: the credit gate, and the leakage-wired launch-window logic.

These suites exist BEFORE any real feature has been computed — the indexer key
does not yet exist — so the first real feature will be born into an already
green canary/prefix discipline rather than retrofitted with one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.config import MissingSecretError, load_config
from data.helius.gate import CREDIT_WEIGHTS, CreditCapError, CreditGate
from research.detection import history as hist

T0 = 1_700_000_000.0


# ------------------------------ the credit gate ---------------------------- #


def test_gate_refuses_when_estimate_exceeds_remaining_and_writes_nothing(
    tmp_path: Path,
) -> None:
    # Arrange — cap 100; a 20-request enhanced sweep weighs 200.
    cfg = load_config()
    object.__setattr__(cfg, "helius_credit_cap", 100)
    gate = CreditGate(cfg, ledger_path=tmp_path / "ledger.jsonl")

    # Act / Assert — refusal names the arithmetic and leaves no ledger behind.
    with pytest.raises(CreditCapError, match="REFUSED"):
        gate.check_estimate(gate.estimate(20, "enhanced"), "sweep")
    with pytest.raises(CreditCapError):
        gate.charge("enhanced", 20, "sweep")
    assert not (tmp_path / "ledger.jsonl").exists()
    assert gate.spent() == 0


def test_gate_ledger_survives_a_restart(tmp_path: Path) -> None:
    # Arrange — charge through one instance, read through a fresh one.
    cfg = load_config()
    object.__setattr__(cfg, "helius_credit_cap", 1_000)
    ledger = tmp_path / "ledger.jsonl"
    first = CreditGate(cfg, ledger_path=ledger)
    first.charge("enhanced", 3, "probe")  # 30 weighted
    first.charge("rpc", 5, "health")  # 5 weighted

    # Act — a new process constructs a new gate over the same file.
    second = CreditGate(cfg, ledger_path=ledger)

    # Assert
    assert second.spent() == 3 * CREDIT_WEIGHTS["enhanced"] + 5 * CREDIT_WEIGHTS["rpc"]
    assert second.remaining() == 1_000 - 35


def test_require_helius_key_raises_naming_the_variable() -> None:
    # Arrange — test the ACCESSOR, not the machine: an environment-dependent
    # assertion here broke the moment the operator added the real key (the
    # C.21 addendum's lesson). Force the absent state explicitly.
    cfg = load_config()
    object.__setattr__(cfg, "helius_api_key", None)

    # Act / Assert
    with pytest.raises(MissingSecretError) as err:
        cfg.require_helius_key()
    assert err.value.missing == ["MLCE_HELIUS_API_KEY"]


# --------------------- window guard: the canary itself --------------------- #


def test_a_label_event_inside_the_window_is_refused_not_clamped() -> None:
    # Act / Assert — an event at T0+10 min sits inside the 30-min window: the
    # computation must refuse, because clamping would leak the event time.
    with pytest.raises(hist.WindowLeakError, match="EXCLUDED"):
        hist.feature_window_end(T0, T0 + 600)
    # An event after the window is fine, and the end is exactly T0+1800.
    assert hist.feature_window_end(T0, T0 + 5_000) == T0 + 1_800.0


def test_features_are_prefix_invariant_beyond_the_window() -> None:
    # Arrange — identical histories except for post-window activity.
    base = [
        hist.Tx(T0, "mint_to", "creator", 1000.0),
        hist.Tx(T0 + 60, "transfer", "early1", 200.0, source="creator"),
        hist.Tx(T0 + 120, "sell", "creator", 100.0),
    ]
    noisy = [*base, hist.Tx(T0 + 3_000, "sell", "creator", 900.0)]

    # Act / Assert — nothing after the window may move any feature.
    assert hist.features(base, T0, "creator", None) == hist.features(noisy, T0, "creator", None)


def test_concentration_and_creator_ttfs_read_inside_the_window_only() -> None:
    # Arrange — creator mints 1000, sends 200 to early1, sells 100 at T0+120.
    txs = [
        hist.Tx(T0, "mint_to", "creator", 1000.0),
        hist.Tx(T0 + 60, "transfer", "early1", 200.0, source="creator"),
        hist.Tx(T0 + 120, "sell", "creator", 100.0),
    ]

    # Act
    out = hist.features(txs, T0, "creator", None)

    # Assert — allocation at T0 is 100%; two holders at window end; TTFS 120 s;
    # early1 is insider-funded; two holders means top-5 covers everything.
    assert out["creator_allocation_t0"] == pytest.approx(1.0)
    assert out["n_early_holders"] == 2.0
    assert out["creator_time_to_first_sell_s"] == pytest.approx(120.0)
    assert out["insider_funded_early_holders"] == 1.0
    assert out["top5_concentration_wend"] == pytest.approx(1.0)


def test_decontamination_thresholds_split_soft_slow_and_honest() -> None:
    # Arrange — insiders hold 1000 at window end; sells timed around the
    # registered 72 h / 30 d horizons at the 70% fraction.
    def txs(sell_ts: float, amount: float) -> list[hist.Tx]:
        return [
            hist.Tx(T0, "mint_to", "creator", 1000.0),
            hist.Tx(sell_ts, "sell", "creator", amount),
        ]

    soft = hist.decontaminate(txs(T0 + 71 * 3_600, 700.0), T0, "creator")
    slow = hist.decontaminate(txs(T0 + 100 * 3_600, 700.0), T0, "creator")
    honest_small = hist.decontaminate(txs(T0 + 71 * 3_600, 699.0), T0, "creator")
    honest_late = hist.decontaminate(txs(T0 + 31 * 86_400, 700.0), T0, "creator")

    # Assert
    assert soft == "soft_rug"
    assert slow == "slow_rug"
    assert honest_small == "honest_candidate"  # 69.9% is below the registered 70%
    assert honest_late == "honest_candidate"  # beyond 30 days is outside both rules
