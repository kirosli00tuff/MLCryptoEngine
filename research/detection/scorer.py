"""Hard-rug safety scorer — the detection track's shipped deliverable (C.24 Task 5).

This packages the one thing the detection track measured as working: separating
**hard rugs** (near-total, ≥ 99% liquidity removal) from other launches on
pre-event launch-window state. C.23 measured that boundary as sharp while the
honest-versus-slow-rug boundary was absent; this module ships the working half as
an artifact and documents, without softening, the question it does **not** answer.

Scope, stated so an output cannot be misread:

- It returns **P(hard_rug)** from launch-window features — the first 30 minutes of
  pool life, the same features C.23 used.
- **Its trustworthy direction is clearance, not alarm.** A *low* score clears a
  pool as not-a-hard-rug at high precision (C.24 measured 0.984, covering ~54% of
  honest pools); a *high* score is a weak rug flag (measured 0.464 precision),
  because honest pools also launch concentrated. C.23's headline 0.984 was this
  clearance (honest-class) direction, not a hard-rug alarm — documented so a high
  score is never misread as a reliable warning.
- It does **not** detect soft or slow rugs; C.23 and C.24 measured that boundary
  as absent from on-chain state at the cutoffs tested. A clearance means "not a
  blatant hard rug", never "safe".
- **Base rate matters.** On the SolRPDS-labelled folds the hard-rug share is a
  large minority; in the wild roughly 99% of launches are scam-adjacent, so this
  is a filter for a small honest minority, not a calibrated general classifier.
  Read a probability against that base rate, carried in :func:`scope_note`.

Creator-history features are deliberately excluded: C.23 measured them inert on
the honest boundary and harmful out of sample, so the scorer uses only the
launch-window concentration / authority / holder features that carried the
signal. The model is persisted by ``train_scorer.py`` and regenerable from the
immutable SolRPDS snapshots via the C.23 fetch pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Launch-window features only (history.features + GoPlus token-security), fixed
# order. Creator-history columns are intentionally absent — see module docstring.
FEATURES: tuple[str, ...] = (
    "creator_allocation_t0",
    "top5_concentration_wend",
    "creator_time_to_first_sell_s",
    "authority_revoked_in_window",
    "n_early_holders",
    "insider_funded_early_holders",
    "freezable",
    "mintable",
    "nontransf",
    "thook",
)

# Sentinel for an unavailable feature — matches the C.23 feature matrix, so a
# model trained on that matrix sees missing values encoded identically at score
# time. A real 0.0 would read as "measured and zero"; this reads as "absent".
MISSING = -1.0


def feature_vector(features: dict[str, float | None]) -> list[float]:
    """Order a feature dict into the model's input vector, missing → sentinel."""
    out: list[float] = []
    for k in FEATURES:
        v = features.get(k)
        out.append(MISSING if v is None else float(v))
    return out


@dataclass(frozen=True)
class HardRugScorer:
    """A loaded booster returning P(hard_rug) from launch-window features."""

    booster: Any  # lightgbm.Booster; kept loose so the module imports without lightgbm
    base_rate: float  # hard-rug prevalence in the training fold, for context

    def probability(self, features: dict[str, float | None]) -> float:
        """P(hard_rug) for one pool's launch-window feature dict, in [0, 1]."""
        pred = self.booster.predict([feature_vector(features)])
        return float(pred[0])


def score_mint(
    mint: str,
    scorer: HardRugScorer,
    fetch_features: Callable[[str], dict[str, float | None]],
) -> float:
    """P(hard_rug) for a pool identifier.

    ``fetch_features`` is injected — in production it is the C.23 launch-window
    pipeline (``research.detection.history.features`` over a Helius fetch of the
    mint), but keeping it a parameter lets the scorer be exercised without a
    vendor key.
    """
    return scorer.probability(fetch_features(mint))


def load_scorer(model_path: Path, base_rate: float) -> HardRugScorer:
    """Load a persisted LightGBM booster into a scorer (lightgbm imported lazily)."""
    import lightgbm as lgb

    return HardRugScorer(booster=lgb.Booster(model_file=str(model_path)), base_rate=base_rate)


def scope_note(
    base_rate: float, clear_precision: float, clear_recall: float, flag_precision: float
) -> str:
    """Scope statement led by the scorer's trustworthy direction (clearance)."""
    return (
        "Hard-rug scorer: outputs P(hard_rug) from 30-minute launch-window state. Its "
        "trustworthy use is CLEARANCE, not alarm. Pools it scores low are cleared as "
        f"not-a-hard-rug at {clear_precision:.3f} precision, covering {clear_recall:.3f} of "
        "honest pools on the 2024 test fold. As a rug ALARM the flag is weak — a high "
        f"P(hard_rug) carries only {flag_precision:.3f} precision — because honest pools also "
        "launch concentrated, so a high score is not a reliable rug warning. It does NOT "
        "detect soft or slow rugs; C.23/C.24 measured that boundary as absent from on-chain "
        f"state. Training-fold hard-rug base rate {base_rate:.3f}; in the wild ~99% of launches "
        "are scam-adjacent, so this filters a small honest minority, not a calibrated "
        "general classifier."
    )
