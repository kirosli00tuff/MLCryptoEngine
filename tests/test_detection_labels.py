"""Tests for the C.20 keyless label layer.

The two that carry the stage's honesty: the monotonic-authority inference must
be one-directional (present-now proves present-at-launch; absent-now proves
nothing), and an unresolved GoPlus lookup must stay ``None`` — collapsing
missing to benign would bias against the positive class, which is exactly the
skew GoPlus coverage already has.
"""

from __future__ import annotations

import pytest

from research.detection import labels as lab


def row(**kw: str) -> dict[str, str]:
    base = {
        "MINT": "So1abcdefghijklmnopqrstuvwxyz1234567890abcd",
        "TOTAL_ADDED_LIQUIDITY": "100.0",
        "TOTAL_REMOVED_LIQUIDITY": "0.0",
        "FIRST_POOL_ACTIVITY_TIMESTAMP": "2024-10-31 23:41:11.000",
        "LAST_POOL_ACTIVITY_TIMESTAMP": "2024-10-31 23:52:02.000",
        "INACTIVITY_STATUS": "Active",
    }
    base.update(kw)
    return base


def test_hard_rug_boundary_is_exactly_99_percent() -> None:
    # Arrange / Act / Assert — the registered threshold, held to the decimal.
    assert lab.is_hard_rug(100.0, 99.0) is True
    assert lab.is_hard_rug(100.0, 98.999) is False
    assert lab.is_hard_rug(0.0, 0.0) is False  # a never-funded pool is not a rug


def test_parse_row_types_fields_and_survives_bad_timestamps() -> None:
    # Arrange
    record = lab.parse_row(row(FIRST_POOL_ACTIVITY_TIMESTAMP="not a date"))

    # Assert — a bad timestamp becomes None, and the lifetime refuses to guess.
    assert record.first_ts is None
    assert record.lifetime_seconds is None
    assert record.added == pytest.approx(100.0)


def test_lifetime_is_the_removal_proxy_and_rejects_reversed_clocks() -> None:
    # Arrange — 23:41:11 -> 23:52:02 is 651 seconds.
    record = lab.parse_row(row())
    assert record.lifetime_seconds == pytest.approx(651.0)

    # Reversed timestamps are a data defect, not a negative lifetime.
    reversed_record = lab.parse_row(
        row(
            FIRST_POOL_ACTIVITY_TIMESTAMP="2024-10-31 23:52:02.000",
            LAST_POOL_ACTIVITY_TIMESTAMP="2024-10-31 23:41:11.000",
        )
    )
    assert reversed_record.lifetime_seconds is None


def test_classify_maps_the_three_pool_classes() -> None:
    # Arrange / Act / Assert
    assert lab.classify(lab.parse_row(row(TOTAL_REMOVED_LIQUIDITY="99.5"))) == lab.HARD_RUG
    assert lab.classify(lab.parse_row(row())) == lab.HONEST_CANDIDATE
    assert lab.classify(lab.parse_row(row(INACTIVITY_STATUS="Inactive"))) == lab.UNLABELED_RESIDUAL


def test_honeypot_reads_dict_and_scalar_forms_and_keeps_unresolved_none() -> None:
    # Arrange / Act / Assert — GoPlus encodes flags both ways.
    assert lab.honeypot_from_goplus({"freezable": {"status": "1", "authority": ["x"]}}) is True
    assert lab.honeypot_from_goplus({"non_transferable": "1"}) is True
    assert lab.honeypot_from_goplus({"freezable": "0", "transfer_hook": None}) is False
    # Unresolved is None, never False: missing coverage skews toward the
    # positive class and must not be read as benign.
    assert lab.honeypot_from_goplus(None) is None
    assert lab.honeypot_from_goplus({}) is None


def test_authority_inference_is_monotonic_one_direction_only() -> None:
    # Arrange / Act / Assert — present-now proves present-at-launch; absent or
    # unknown proves nothing. The asymmetry IS the rule (ADR-045).
    assert lab.authority_pre_event(True) == "pre_event_present"
    assert lab.authority_pre_event(False) == "indeterminate"
    assert lab.authority_pre_event(None) == "indeterminate"


def test_baselines_use_actual_counts_and_leave_undefined_precision_none() -> None:
    # Arrange — 30 honest of 100.
    base = lab.baselines(30, 100)

    # Assert — always-rug predicts no honest tokens: precision is 0/0 and must
    # be None, never coerced to 0 or 1; the other two sit at the base rate.
    assert base["always_rug"]["honest_precision"] is None
    assert base["always_rug"]["honest_recall"] == 0.0
    assert base["always_honest"]["honest_precision"] == pytest.approx(0.30)
    assert base["always_honest"]["honest_recall"] == 1.0
    assert base["random_at_base_rate"]["honest_precision"] == pytest.approx(0.30)
    assert base["random_at_base_rate"]["honest_recall"] == pytest.approx(0.30)
