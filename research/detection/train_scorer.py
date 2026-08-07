"""Regenerate and persist the hard-rug scorer (C.24 Task 5).

Reads the C.23 launch-window feature matrix, fits a LightGBM booster to separate
hard rugs (positive) from other launches on the registered time split (train
≤ 2023, test 2024), evaluates the **hard-rug-class** precision-recall curve on the
2024 fold, and persists the booster plus a scope sidecar. Run:

    python -m research.detection.train_scorer

The model lands under ``data/processed/`` (gitignored, regenerable from the
immutable SolRPDS snapshots via the C.23 fetch pipeline); the measured operating
point is printed and written to the sidecar for the report and the scorer's
documented scope. Model class and hyperparameters match C.23 exactly — no search.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

from research.detection.scorer import FEATURES, MISSING, scope_note

MATRIX = Path("data/processed/detection/features_c23.csv")
MODEL = Path("data/processed/detection/hard_rug_scorer.txt")
META = Path("data/processed/detection/hard_rug_scorer.meta.json")


def _vec(row: dict[str, str]) -> list[float]:
    out: list[float] = []
    for k in FEATURES:
        v = row.get(k, "")
        out.append(MISSING if v in ("", "None") else float(v))
    return out


def load_matrix() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Feature matrix, hard-rug label (positive), and year vector from the CSV."""
    with MATRIX.open() as fh:
        rows = list(csv.DictReader(fh))
    x = np.array([_vec(r) for r in rows])
    y = np.array([1 if r["cls"] == "hard_rug" else 0 for r in rows])
    yr = np.array([r["year"] for r in rows])
    return x, y, yr


def pr_at_recall(y: np.ndarray, p: np.ndarray, min_recall: float = 0.5) -> dict[str, float]:
    """Max-precision operating point subject to recall ≥ ``min_recall``."""
    order = np.argsort(-p)
    ys = y[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    prec = tp / (tp + fp)
    rec = tp / max(1, int(ys.sum()))
    ok = rec >= min_recall
    if not ok.any():
        return {"precision": 0.0, "recall": 0.0, "threshold": 1.0}
    i = int(np.argmax(np.where(ok, prec, -1.0)))
    return {"precision": float(prec[i]), "recall": float(rec[i]), "threshold": float(p[order][i])}


def main() -> None:
    x, y, yr = load_matrix()
    tr = yr != "2024"
    te = ~tr
    base_rate = float(y[tr].mean())
    model = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, verbose=-1)
    model.fit(x[tr], y[tr])
    p = np.asarray(model.predict_proba(x[te]))[:, 1]
    # Two directions on the same separator: FLAG (predict hard_rug, score = P) is
    # weak; CLEAR (predict honest, score = 1 - P) is the strong, useful one.
    flag = pr_at_recall(y[te], p)
    clear = pr_at_recall(1 - y[te], 1.0 - p)
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(MODEL))
    meta = {
        "features": list(FEATURES),
        "train_n": int(tr.sum()),
        "train_hard_rug": int(y[tr].sum()),
        "test_n": int(te.sum()),
        "test_hard_rug": int(y[te].sum()),
        "base_rate_train": round(base_rate, 4),
        "clearance_point_pos_honest_recall_ge_0.5": {k: round(v, 4) for k, v in clear.items()},
        "flag_point_pos_hard_rug_recall_ge_0.5": {k: round(v, 4) for k, v in flag.items()},
        "scope": scope_note(base_rate, clear["precision"], clear["recall"], flag["precision"]),
    }
    META.write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
