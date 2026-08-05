"""Leakage probes aimed at the deep path specifically.

``tests/test_leakage.py`` already guards the *feature* library: no feature
correlates with a planted future value, and features are prefix-invariant. Those
probes protect a tabular model completely and a windowed model only partly. A
sequential model adds an input transformation the feature tests never see —
:func:`research.deep.models.make_windows` — and one misaligned index there puts
a bar from *after* the sample inside its own window. Nothing raises. AUC simply
improves.

Three probes run here, and the third is the one that matters.

**Window causality** is structural: every source row a window reads must have an
index no greater than the sample's own. Cheap, exhaustive, fails loudly.

**The planted-future canary** proves the detector works at all. A column equal to
the future return is added to the features, and the deep model must find it —
AUC near 1.0. A probe that cannot detect a deliberate leak proves nothing when it
reports a clean result, which is this project's standing "a check that cannot
fail is not a check" rule turned on the check itself.

**The label-shift control** is the real test. Labels are rolled far forward, so
each sample trains against a label belonging to a different, much later sample.
With honest windows that destroys the relationship and AUC collapses to about
0.5. If AUC stays high, the model is reading something it should not — and the
pre-registration says any improvement failing this is reported as a leak rather
than a discovery.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.deep import models
from research.diagnostics import confidence as cf
from research.labels.fixed_horizon import embargo_ns_for

# A canary the model cannot see is a broken canary, so the bar is strict.
CANARY_MIN_AUC = 0.90
# A shifted label carries no information; past this, something is read ahead.
SHIFT_MAX_AUC = 0.55
# Probes run on a subsample: they answer a yes/no question about the input path,
# not a question about performance, and the full range would cost hours.
PROBE_ROWS = 40_000
PROBE_SPLITS = 3
PROBE_HORIZON_MS = 1000
# Far enough forward that no purge or embargo could make the pairing legitimate.
LABEL_SHIFT_ROWS = 5000


def probe_config(base: models.DeepConfig) -> models.DeepConfig:
    """Training settings for the probes, deliberately stronger than production.

    A probe's job is to *find* a leak, so it must be able to fit one. The
    production config trains 6 epochs at batch 1024, which on a 40,000-row probe
    subsample is a few hundred gradient steps — enough for a real signal and not
    reliably enough for the canary to reach AUC 0.90 on a planted column. An
    underpowered canary reports "clean" for the wrong reason, and every clean
    result behind it would then be worthless.

    This is not hyperparameter search: it makes the *detector* sensitive, and it
    never touches the models whose results are compared against the bar.
    """
    return models.DeepConfig(
        hidden=base.hidden,
        layers=base.layers,
        window=base.window,
        epochs=20,
        batch_size=256,
        learning_rate=3e-3,
        weight_decay=base.weight_decay,
        dropout=0.0,
        seed=base.seed,
        max_train_rows=base.max_train_rows,
    )


def _subsample(
    ts: NDArray[np.int64], features: NDArray[np.float64], ret: NDArray[np.float64]
) -> tuple[NDArray[np.int64], NDArray[np.float64], NDArray[np.float64]]:
    """The most recent ``PROBE_ROWS`` rows, contiguous and in order.

    Contiguous rather than random: a windowed model needs its neighbours, and
    sampling at random would destroy the very structure under test.
    """
    usable = ~np.isnan(ret)
    ts_u, x_u, ret_u = ts[usable], features[usable], ret[usable]
    if ts_u.size > PROBE_ROWS:
        ts_u, x_u, ret_u = ts_u[-PROBE_ROWS:], x_u[-PROBE_ROWS:], ret_u[-PROBE_ROWS:]
    return ts_u, x_u, ret_u


def _oof_auc(
    ts: NDArray[np.int64],
    features: NDArray[np.float64],
    y01: NDArray[np.int64],
    cfg: models.DeepConfig | None = None,
) -> float:
    prob = models.fit_oof(
        "gru",
        ts,
        features,
        y01,
        PROBE_HORIZON_MS,
        PROBE_SPLITS,
        embargo_ns_for((PROBE_HORIZON_MS,)),
        probe_config(cfg or models.DeepConfig()),
    )
    covered = ~np.isnan(prob)
    if int(covered.sum()) < cf.MIN_SAMPLES:
        return float("nan")
    return cf.auc_score(y01[covered], prob[covered])


def window_causality(window: int, n: int = 512) -> dict[str, Any]:
    """No window may read a row later than the sample it belongs to."""
    offenders = [
        {"index": i, "reads": sorted(set(models.window_contains_only_past(window, i)))}
        for i in range(n)
        if max(models.window_contains_only_past(window, i)) > i
    ]
    return {
        "probe": "window_causality",
        "window_bars": window,
        "rows_checked": n,
        "offenders": offenders[:5],
        "passed": not offenders,
        "means": "every windowed input row index is <= the sample's own index",
    }


def planted_future_canary(
    ts: NDArray[np.int64],
    features: NDArray[np.float64],
    ret: NDArray[np.float64],
    cfg: models.DeepConfig | None = None,
) -> dict[str, Any]:
    """Add a column that IS the future. The model must find it, or the probe is blind."""
    ts_u, x_u, ret_u = _subsample(ts, features, ret)
    if ts_u.size < cf.MIN_SAMPLES:
        return {"probe": "planted_future_canary", "skipped": "too few rows"}
    auc = _oof_auc(ts_u, np.column_stack([x_u, ret_u]), (ret_u > 0).astype(np.int64), cfg)
    return {
        "probe": "planted_future_canary",
        "auc_with_planted_future": round(float(auc), 4),
        "threshold": CANARY_MIN_AUC,
        "passed": bool(auc >= CANARY_MIN_AUC),
        "means": "the probe can detect a deliberate leak, so a clean result elsewhere means something",
    }


def label_shift_control(
    ts: NDArray[np.int64],
    features: NDArray[np.float64],
    ret: NDArray[np.float64],
    cfg: models.DeepConfig | None = None,
) -> dict[str, Any]:
    """Pair each sample with a far-later label. Honest windows collapse to chance."""
    ts_u, x_u, ret_u = _subsample(ts, features, ret)
    if ts_u.size < LABEL_SHIFT_ROWS + cf.MIN_SAMPLES:
        return {"probe": "label_shift_control", "skipped": "too few rows"}
    shifted = ret_u[LABEL_SHIFT_ROWS:]
    auc = _oof_auc(
        ts_u[:-LABEL_SHIFT_ROWS], x_u[:-LABEL_SHIFT_ROWS], (shifted > 0).astype(np.int64), cfg
    )
    return {
        "probe": "label_shift_control",
        "shift_rows": LABEL_SHIFT_ROWS,
        "auc_on_shifted_labels": round(float(auc), 4),
        "threshold": SHIFT_MAX_AUC,
        "passed": bool(auc <= SHIFT_MAX_AUC),
        "means": "with labels detached from their samples the model learns nothing",
    }


def run_probes(
    ts: NDArray[np.int64],
    features: NDArray[np.float64],
    data: dict[str, Any],
    cfg: models.DeepConfig,
    n_splits: int,
) -> dict[str, Any]:
    """All three probes, with a single pass/fail the caller can act on."""
    column = f"ret_bps_{PROBE_HORIZON_MS}ms"
    if column not in data:
        return {"error": f"{column} absent; probes need a short horizon", "all_passed": False}
    ret = data[column].astype(np.float64)
    probes = [
        window_causality(cfg.window),
        planted_future_canary(ts, features, ret, cfg),
        label_shift_control(ts, features, ret, cfg),
    ]
    ran = [p for p in probes if "skipped" not in p]
    return {
        "probes": probes,
        "n_splits_used": PROBE_SPLITS,
        "rows_used": PROBE_ROWS,
        "baseline_n_splits": n_splits,
        "all_passed": bool(ran) and all(bool(p.get("passed")) for p in ran),
        "policy": (
            "Any improvement that fails a probe is treated as a LEAK, not a discovery. "
            "Decided in progress.md commit a2d7466, before training."
        ),
    }
