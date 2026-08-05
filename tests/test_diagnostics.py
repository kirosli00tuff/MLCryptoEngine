"""Tests for the C.14 confidence-versus-magnitude diagnostic.

The two that matter are
:func:`test_analyse_recovers_a_planted_confidence_to_magnitude_relationship` and
:func:`test_analyse_reports_no_relationship_when_magnitude_is_independent_of_sign`.
They construct the two worlds the diagnostic exists to tell apart — a model
sure about moves worth trading, and a model sure about noise — and assert it
reaches opposite conclusions. A diagnostic that answered "no relationship" in
both would confirm nothing; it would just be a constant, and a null result from
it would mean nothing either.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.diagnostics import confidence as cf

NS_PER_S = 1_000_000_000


def _report(
    horizon_ms: int,
    rho: float,
    decile_capture: float,
    all_capture: float,
    calibration_error: float = 0.0,
) -> cf.ConfidenceReport:
    return cf.ConfidenceReport(
        horizon_ms=horizon_ms,
        n=10_000,
        auc=0.9,
        gross_capture_all=all_capture,
        spearman_conf_vs_magnitude=rho,
        top_slice_capture={"decile": decile_capture},
        top_slice_ratio={"decile": decile_capture / all_capture if all_capture else float("nan")},
        max_calibration_error=calibration_error,
    )


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #


def test_gross_capture_goes_long_above_half_and_short_below() -> None:
    # Arrange — a confident long into a rise and a confident short into a fall.
    # Both are correct calls, so both must contribute positively.
    # Act & Assert — (+4 + +6) / 2 = 5.
    assert cf.gross_capture(np.array([0.9, 0.1]), np.array([4.0, -6.0])) == pytest.approx(5.0)


def test_gross_capture_is_negative_when_the_model_is_confidently_wrong() -> None:
    # Arrange / Act / Assert
    assert cf.gross_capture(np.array([0.9, 0.1]), np.array([-4.0, 6.0])) == pytest.approx(-5.0)


def test_auc_is_one_on_perfect_separation_and_half_on_a_constant_score() -> None:
    # Arrange
    y = np.array([0, 0, 1, 1])

    # Act & Assert
    assert cf.auc_score(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)
    assert cf.auc_score(y, np.array([0.9, 0.8, 0.2, 0.1])) == pytest.approx(0.0)
    assert cf.auc_score(y, np.array([0.5, 0.5, 0.5, 0.5])) == pytest.approx(0.5)


def test_ranking_averages_ties_rather_than_inventing_an_order() -> None:
    # Arrange — confidence piles up at one value when a fold degenerates.
    # Act
    ranks = cf._rank(np.array([1.0, 2.0, 2.0, 3.0]))

    # Assert — the tied pair share the mean of their two ranks.
    assert ranks.tolist() == [0.0, 1.5, 1.5, 3.0]


# --------------------------------------------------------------------------- #
# calibration: accurate, or merely rank-ordered
# --------------------------------------------------------------------------- #


def test_calibration_separates_accurate_probabilities_from_merely_ordered_ones() -> None:
    # Arrange — a calibrated model, where p=0.85 is right about 85% of the time.
    rng = np.random.default_rng(3)
    prob = np.repeat([0.15, 0.45, 0.85], 4000)
    y01 = (rng.random(prob.size) < prob).astype(np.int64)
    # Same ordering, squashed toward 0.5: identical AUC, ruined calibration.
    squashed = 0.5 + (prob - 0.5) * 0.1

    # Act
    _, brier_good, worst_good = cf.calibration(prob, y01)
    _, brier_bad, worst_bad = cf.calibration(squashed, y01)

    # Assert — AUC cannot tell these apart because it reads only the ordering.
    # That is exactly why the stage reports calibration beside it.
    assert cf.auc_score(y01, prob) == pytest.approx(cf.auc_score(y01, squashed))
    assert worst_good < 0.02
    assert worst_bad > 0.10
    assert brier_bad > brier_good


# --------------------------------------------------------------------------- #
# verdict against the pre-registered bars
# --------------------------------------------------------------------------- #


def test_verdict_confirms_closure_when_confidence_tracks_only_tiny_moves() -> None:
    # Arrange — |rho| under 0.05 everywhere and a top decile that buys nothing.
    reports = [
        _report(100, rho=0.01, decile_capture=0.04, all_capture=0.03),
        _report(900_000, rho=-0.02, decile_capture=3.5, all_capture=3.31),
    ]

    # Act & Assert
    assert cf.verdict(reports, round_trip_cost_bps=80.0)["outcome"] == "CONFIRMS CLOSURE"


def test_verdict_finds_a_filter_when_confidence_tracks_large_moves() -> None:
    # Arrange — a real relationship and a top decile worth three times the mean.
    reports = [
        _report(100, rho=0.31, decile_capture=0.09, all_capture=0.03),
        _report(900_000, rho=0.22, decile_capture=11.0, all_capture=3.31),
    ]

    # Act & Assert — weak, because 11 bps still cannot pay an 80 bps round trip.
    assert cf.verdict(reports, round_trip_cost_bps=80.0)["outcome"] == "FILTER EXISTS (weak)"


def test_verdict_calls_a_filter_economic_only_when_it_clears_the_round_trip() -> None:
    # Arrange — the top decile finally exceeds the cost of trading it.
    reports = [_report(900_000, rho=0.40, decile_capture=95.0, all_capture=3.31)]

    # Act & Assert — the ONLY outcome that would reopen H1 on evidence.
    assert cf.verdict(reports, round_trip_cost_bps=80.0)["outcome"] == "FILTER IS ECONOMIC (strong)"


def test_a_large_negative_rho_does_not_satisfy_the_filter_exists_branch() -> None:
    # Arrange — this is the world that actually occurred on Kraken: confidence
    # strongly ANTI-correlated with magnitude, while the top-confidence decile
    # still captures more than twice the mean because its calls are far more
    # accurate. The registered text gates that branch on "rho >= 0.10", whose
    # stated meaning is "high-confidence predictions concentrate in LARGER
    # moves". A rho of -0.31 is the opposite claim and must not pass it.
    reports = [
        _report(100, rho=-0.31, decile_capture=0.096, all_capture=0.032),
        _report(1000, rho=-0.21, decile_capture=0.344, all_capture=0.101),
    ]

    # Act
    found = cf.verdict(reports, round_trip_cost_bps=80.0)

    # Assert — not a filter, and not "confirms closure" either, since |rho| is
    # nowhere near zero. The bar says inconclusive, and the direction field is
    # what carries the actual finding.
    assert found["outcome"] == "INCONCLUSIVE"
    assert "SMALLER moves" in found["direction"]
    assert found["min_signed_spearman"] == pytest.approx(-0.31)


def test_verdict_refuses_to_round_an_ambiguous_result_toward_either_side() -> None:
    # Arrange — rho above the confirms-closure ceiling, below the filter floor.
    reports = [_report(900_000, rho=0.07, decile_capture=4.5, all_capture=3.31)]

    # Act & Assert — pre-registration says report it, do not nudge it.
    assert cf.verdict(reports, round_trip_cost_bps=80.0)["outcome"] == "INCONCLUSIVE"


# --------------------------------------------------------------------------- #
# the diagnostic end to end, on both worlds it must distinguish
# --------------------------------------------------------------------------- #


def test_analyse_recovers_a_planted_confidence_to_magnitude_relationship() -> None:
    # Arrange — a feature genuinely predicts the sign, and it predicts the
    # LARGE moves best. A working diagnostic must see positive rho here; if it
    # cannot, a null result anywhere else is meaningless.
    rng = np.random.default_rng(11)
    n = 6000
    signal = rng.normal(0.0, 1.0, n)
    ret = np.sign(signal) * np.abs(signal) * 5.0 + rng.normal(0.0, 0.5, n)
    features = np.column_stack([signal, rng.normal(0.0, 1.0, n)])
    ts = np.arange(n, dtype=np.int64) * NS_PER_S

    # Act
    found = cf.analyse(ts, features, ret, horizon_ms=1000, n_splits=3, embargo_ns=NS_PER_S)

    # Assert
    assert found is not None
    assert found.spearman_conf_vs_magnitude > 0.2
    assert found.top_slice_capture["decile"] > found.gross_capture_all


def test_analyse_reports_no_relationship_when_magnitude_is_independent_of_sign() -> None:
    # Arrange — the sign is highly predictable but magnitude is independent
    # noise. This is the H1 hypothesis in synthetic form: superb AUC, and
    # confidence that says nothing about whether a move is worth trading.
    rng = np.random.default_rng(13)
    n = 6000
    signal = rng.normal(0.0, 1.0, n)
    ret = np.sign(signal) * np.abs(rng.normal(0.0, 5.0, n))
    features = np.column_stack([signal, rng.normal(0.0, 1.0, n)])
    ts = np.arange(n, dtype=np.int64) * NS_PER_S

    # Act
    found = cf.analyse(ts, features, ret, horizon_ms=1000, n_splits=3, embargo_ns=NS_PER_S)

    # Assert — near-perfect discrimination carrying no magnitude information.
    assert found is not None
    assert found.auc > 0.9
    assert abs(found.spearman_conf_vs_magnitude) < 0.10


def test_oof_predictions_return_only_samples_a_fold_actually_covered() -> None:
    # Arrange
    rng = np.random.default_rng(5)
    n = 2000
    features = rng.normal(0.0, 1.0, (n, 3))
    ret = features[:, 0] + rng.normal(0.0, 0.1, n)
    ts = np.arange(n, dtype=np.int64) * NS_PER_S

    # Act
    prob, kept, y01 = cf.oof_predictions(ts, features, ret, 1000, 3, NS_PER_S)

    # Assert — no NaN survives, and an uncovered sample is dropped rather than
    # scored as a confident zero.
    assert prob.size == kept.size == y01.size
    assert not np.isnan(prob).any()
    assert prob.size <= n
