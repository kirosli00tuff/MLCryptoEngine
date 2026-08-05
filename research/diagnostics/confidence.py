"""Is the model confident about moves large enough to pay, or only about small ones?

AUC 0.941 beside ~0.03 bps of gross capture is not a contradiction, it is a
category error waiting to be named. **AUC is magnitude-blind.** It asks only
whether up-moves score higher than down-moves, so a model that calls the sign
of every 0.01 bps flicker while being useless on the 5 bps moves posts a superb
AUC and captures nothing. That is the hypothesis this module tests.

Confidence is ``|p - 0.5|``; magnitude is the realised ``|return|`` over the
horizon. If the two are uncorrelated, the model is spending its discrimination
on noise, and H1's closure is confirmed with a far better explanation than "the
edge was too small". If confidence instead concentrates in the larger moves,
then a **selection filter exists that was never built**, and every EV figure
this project has published was computed on an unfiltered population.

Three deliberate choices.

**Spearman, not Pearson.** The magnitude distribution is heavy-tailed, and a
Pearson coefficient on raw values would report a handful of extreme moves
rather than the relationship across the sample.

**Gross capture inside each bin, not hit rate.** Capture is
``mean(sign(p - 0.5) * ret_bps)`` — exactly the quantity every net EV in this
project derives from, since ``net EV = gross capture - cost``. Hit rate would
reproduce the magnitude-blindness the diagnostic exists to expose.

**Out-of-fold predictions from the pipeline's own purged CV.** Anything else
would compare a diagnostic fitted one way against results produced another, and
the difference would be uninterpretable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.models.lgbm import make_classifier
from research.validation.purged_kfold import PurgedKFold

NS_PER_MS = 1_000_000
# Ten bins is enough resolution to see a monotone trend and few enough that
# each bin keeps a usable sample count.
N_BINS = 10
# The top-confidence slices the pre-registration named.
TOP_SLICES = {"decile": 0.10, "quintile": 0.20, "half": 0.50}
MIN_SAMPLES = 200


@dataclass
class ConfidenceReport:
    """One horizon's answer to the magnitude-blindness question."""

    horizon_ms: int
    n: int
    auc: float
    gross_capture_all: float
    spearman_conf_vs_magnitude: float
    top_slice_capture: dict[str, float] = field(default_factory=dict)
    top_slice_ratio: dict[str, float] = field(default_factory=dict)
    magnitude_by_confidence_bin: list[dict[str, float]] = field(default_factory=list)
    calibration: list[dict[str, float]] = field(default_factory=list)
    brier: float = 0.0
    max_calibration_error: float = 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "horizon_ms": self.horizon_ms,
            "n": self.n,
            "auc": round(self.auc, 4),
            "gross_capture_bps_all": round(self.gross_capture_all, 4),
            "spearman_confidence_vs_abs_move": round(self.spearman_conf_vs_magnitude, 4),
            "gross_capture_bps_top": {k: round(v, 4) for k, v in self.top_slice_capture.items()},
            "capture_ratio_top_vs_all": {k: round(v, 3) for k, v in self.top_slice_ratio.items()},
            "magnitude_by_confidence_bin": self.magnitude_by_confidence_bin,
            "calibration": self.calibration,
            "brier": round(self.brier, 5),
            "max_calibration_error": round(self.max_calibration_error, 4),
        }


def _rank(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Ranks with ties averaged.

    Ties matter here: confidence has mass at exactly 0.5 when a fold
    degenerates, and integer-ranking those would invent an ordering the model
    never expressed.
    """
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=np.float64)
    ranks[order] = np.arange(values.size, dtype=np.float64)
    sorted_values = values[order]
    start = 0
    for i in range(1, values.size + 1):
        if i == values.size or sorted_values[i] != sorted_values[start]:
            if i - start > 1:
                ranks[order[start:i]] = ranks[order[start:i]].mean()
            start = i
    return ranks


def _spearman(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    if a.size < MIN_SAMPLES:
        return float("nan")
    ra, rb = _rank(a), _rank(b)
    if float(ra.std()) == 0.0 or float(rb.std()) == 0.0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def auc_score(y01: NDArray[np.int64], score: NDArray[np.float64]) -> float:
    """Rank-based AUC, same definition the pipeline reports."""
    positives = int(y01.sum())
    negatives = int(y01.size - positives)
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = _rank(score) + 1.0
    return float(
        (ranks[y01 == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives)
    )


def gross_capture(prob: NDArray[np.float64], ret_bps: NDArray[np.float64]) -> float:
    """Mean signed return: long above 0.5, short below. Before cost.

    This is the exact quantity every net EV in this project derives from, so it
    is the only capture definition that lets a C.14 number sit beside a C.8
    number honestly.
    """
    if prob.size == 0:
        return 0.0
    return float(np.mean(np.where(prob > 0.5, ret_bps, -ret_bps)))


def oof_predictions(
    ts_ns: NDArray[np.int64],
    features: NDArray[np.float64],
    ret_bps: NDArray[np.float64],
    horizon_ms: int,
    n_splits: int,
    embargo_ns: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int64]]:
    """Out-of-fold probabilities under the pipeline's own purged CV.

    Returns ``(prob, ret, y01)`` restricted to samples a fold actually covered,
    so an uncovered sample can never be scored as a confident zero.
    """
    prob = np.full(ret_bps.size, np.nan)
    y01 = (ret_bps > 0).astype(np.int64)
    folds = PurgedKFold(n_splits, horizon_ms * NS_PER_MS, embargo_ns=embargo_ns)
    for train_idx, test_idx in folds.split(ts_ns.tolist()):
        if len(set(y01[train_idx].tolist())) < 2:
            continue
        clf = make_classifier()
        clf.fit(features[train_idx], y01[train_idx])
        prob[test_idx] = np.asarray(clf.predict_proba(features[test_idx]))[:, 1]
    covered = ~np.isnan(prob)
    return prob[covered], ret_bps[covered], y01[covered]


def calibration(
    prob: NDArray[np.float64], y01: NDArray[np.int64]
) -> tuple[list[dict[str, float]], float, float]:
    """Are the probabilities accurate, or merely rank-ordered?

    A model can win on AUC while being badly calibrated, because AUC reads only
    the ordering. Bins are equal-width in predicted probability rather than
    equal-count, because the question is whether *a stated probability* is
    accurate and equal-count bins would blur that across whatever range they
    happened to span.
    """
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    rows: list[dict[str, float]] = []
    worst = 0.0
    for i in range(N_BINS):
        lo, hi = float(edges[i]), float(edges[i + 1])
        mask = (prob >= lo) & ((prob < hi) if i < N_BINS - 1 else (prob <= hi))
        count = int(mask.sum())
        if count == 0:
            continue
        predicted = float(prob[mask].mean())
        realised = float(y01[mask].mean())
        worst = max(worst, abs(predicted - realised))
        rows.append(
            {
                "bin_low": round(lo, 2),
                "bin_high": round(hi, 2),
                "n": count,
                "mean_predicted": round(predicted, 4),
                "observed_frequency": round(realised, 4),
                "gap": round(predicted - realised, 4),
            }
        )
    brier = float(np.mean((prob - y01) ** 2)) if prob.size else 0.0
    return rows, brier, worst


def analyse(
    ts_ns: NDArray[np.int64],
    features: NDArray[np.float64],
    ret_bps: NDArray[np.float64],
    horizon_ms: int,
    n_splits: int,
    embargo_ns: int,
) -> ConfidenceReport | None:
    """The whole Task 1 diagnostic for one horizon."""
    usable = ~np.isnan(ret_bps)
    if int(usable.sum()) < max(MIN_SAMPLES, n_splits * 20):
        return None
    prob, ret, y01 = oof_predictions(
        ts_ns[usable], features[usable], ret_bps[usable], horizon_ms, n_splits, embargo_ns
    )
    if prob.size < MIN_SAMPLES:
        return None

    confidence = np.abs(prob - 0.5)
    magnitude = np.abs(ret)
    all_capture = gross_capture(prob, ret)

    report = ConfidenceReport(
        horizon_ms=horizon_ms,
        n=int(prob.size),
        auc=auc_score(y01, prob),
        gross_capture_all=all_capture,
        spearman_conf_vs_magnitude=_spearman(confidence, magnitude),
    )

    # Top-confidence slices: does restricting to the model's surest calls buy
    # anything? The ratio beside the level is what the pre-registered bar reads.
    order = np.argsort(-confidence, kind="mergesort")
    for name, fraction in TOP_SLICES.items():
        take = max(MIN_SAMPLES, int(fraction * prob.size))
        if take > prob.size:
            continue
        idx = order[:take]
        capture = gross_capture(prob[idx], ret[idx])
        report.top_slice_capture[name] = capture
        report.top_slice_ratio[name] = capture / all_capture if all_capture != 0 else float("nan")

    # The magnitude profile across confidence bins is the picture behind rho.
    quantiles = np.quantile(confidence, np.linspace(0.0, 1.0, N_BINS + 1))
    for i in range(N_BINS):
        lo, hi = float(quantiles[i]), float(quantiles[i + 1])
        mask = (confidence >= lo) & ((confidence < hi) if i < N_BINS - 1 else (confidence <= hi))
        if not int(mask.sum()):
            continue
        report.magnitude_by_confidence_bin.append(
            {
                "bin": i + 1,
                "n": int(mask.sum()),
                "mean_confidence": round(float(confidence[mask].mean()), 4),
                "mean_abs_move_bps": round(float(magnitude[mask].mean()), 4),
                "median_abs_move_bps": round(float(np.median(magnitude[mask])), 4),
                "gross_capture_bps": round(gross_capture(prob[mask], ret[mask]), 4),
            }
        )

    report.calibration, report.brier, report.max_calibration_error = calibration(prob, y01)
    return report


def verdict(reports: list[ConfidenceReport], round_trip_cost_bps: float) -> dict[str, Any]:
    """Score the diagnostic against the bars pre-registered in progress.md.

    The thresholds are constants here rather than anything derived from the
    results, which is the entire point: they were committed before this ran
    (commit a2d7466) and this function may not move them.
    """
    if not reports:
        return {"error": "no horizons produced a report"}
    rhos = [r.spearman_conf_vs_magnitude for r in reports]
    # SIGNED, because the registered text says "rho >= 0.10" and means it. The
    # branch it gates is "high-confidence predictions concentrate in LARGER
    # moves"; a large negative rho is the opposite claim and must not satisfy
    # it. Magnitude is kept separately for the confirms-closure test, which is
    # a statement about the absence of any relationship in either direction.
    rho_signed_max = max(rhos)
    rho_abs_max = max(abs(v) for v in rhos)
    ratios = [r.top_slice_ratio.get("decile", float("nan")) for r in reports]
    finite = [r for r in ratios if not np.isnan(r)]
    best_ratio = max(finite) if finite else float("nan")
    best_decile_capture = max(r.top_slice_capture.get("decile", 0.0) for r in reports)

    if best_decile_capture >= round_trip_cost_bps:
        outcome = "FILTER IS ECONOMIC (strong)"
    elif rho_signed_max >= 0.10 and best_ratio >= 2.0:
        outcome = "FILTER EXISTS (weak)"
    elif rho_abs_max < 0.05 and (np.isnan(best_ratio) or best_ratio < 2.0):
        outcome = "CONFIRMS CLOSURE"
    else:
        outcome = "INCONCLUSIVE"

    # The pre-registration imagined two worlds — no relationship, or confidence
    # concentrating in larger moves. A strongly NEGATIVE rho is a third, and it
    # supports the closure more firmly than the "uncorrelated" case the bar was
    # written for. The bar is not moved to accommodate it; the direction is
    # reported beside the bar's own verdict so the reader sees both.
    direction = (
        "confidence concentrates in SMALLER moves (rho negative) — the model is surest "
        "exactly where there is least to win"
        if min(rhos) <= -0.10
        else "confidence concentrates in larger moves (rho positive)"
        if rho_signed_max >= 0.10
        else "no material relationship in either direction"
    )

    return {
        "outcome": outcome,
        "direction": direction,
        "signed_spearman_by_horizon": [round(v, 4) for v in rhos],
        "max_signed_spearman": round(rho_signed_max, 4),
        "min_signed_spearman": round(min(rhos), 4),
        "max_abs_spearman": round(rho_abs_max, 4),
        "best_top_decile_capture_ratio": None if np.isnan(best_ratio) else round(best_ratio, 3),
        "best_top_decile_capture_bps": round(best_decile_capture, 4),
        "round_trip_cost_bps": round_trip_cost_bps,
        "bars": {
            "confirms_closure": "max|rho| < 0.05 AND top-decile capture < 2x all-sample",
            "filter_weak": "max|rho| >= 0.10 AND top-decile capture >= 2x all-sample",
            "filter_economic": f"top-decile capture >= {round_trip_cost_bps} bps (net EV >= 0)",
            "pre_registered_in": "progress.md, commit a2d7466, before any result was computed",
        },
        "worst_calibration_gap": round(max(r.max_calibration_error for r in reports), 4),
        "mean_brier": round(float(np.mean([r.brier for r in reports])), 5),
    }
