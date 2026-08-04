"""Screen every pair, then correct for having screened every pair.

The arithmetic that makes this stage's headline number honest: testing *N*
pairs at a 5% threshold produces about ``0.05 * N`` rejections when nothing is
cointegrated at all. On a 58-symbol universe that is 1,653 tests and roughly 83
spurious "discoveries" — enough to fill a results table, sort it by Sharpe, and
publish the top ten. The pairs-trading literature is full of exactly this
artifact, and it is indistinguishable from a real finding unless the correction
is applied before anyone looks at the winners.

Benjamini-Hochberg controls the *false discovery rate*: the expected share of
rejections that are false. Preferred here over Bonferroni, which controls the
probability of even one false rejection and on 1,653 tests would be so
conservative that a real relationship of ordinary strength could not survive
it. What matters for a trading decision is "how much of this table is noise",
and that is the quantity BH bounds.

Both counts are always reported. The raw count is never deleted, because the
gap between raw and corrected *is* the finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import numpy as np
from statsmodels.stats.multitest import multipletests

from data.archive.series import PriceMatrix
from research.pairs.cointegration import EngleGranger, Johansen, engle_granger, johansen

ALPHA = 0.05
FDR_METHOD = "fdr_bh"
MIN_OVERLAP = 250


@dataclass(frozen=True)
class PairResult:
    """One pair's screening outcome under both tests."""

    left: str
    right: str
    eg: EngleGranger
    joh: Johansen | None

    @property
    def key(self) -> str:
        return f"{self.left}/{self.right}"


@dataclass
class ScreenResult:
    """Every tested pair plus the multiple-testing accounting."""

    pairs: list[PairResult] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    alpha: float = ALPHA
    rejected_bh: list[bool] = field(default_factory=list)
    q_values: list[float] = field(default_factory=list)
    window: str = ""

    @property
    def tested(self) -> int:
        return len(self.pairs)

    @property
    def raw_hits(self) -> int:
        """Pairs below alpha with no correction at all."""
        return sum(1 for p in self.pairs if p.eg.p_value < self.alpha)

    @property
    def expected_false_positives(self) -> float:
        """How many rejections pure chance produces at this universe size."""
        return self.alpha * self.tested

    @property
    def corrected_hits(self) -> int:
        return sum(self.rejected_bh)

    @property
    def johansen_hits(self) -> int:
        return sum(1 for p in self.pairs if p.joh is not None and p.joh.rejects_no_cointegration)

    def survivors(self) -> list[PairResult]:
        """Pairs that survive BH, strongest first."""
        keep = [p for p, r in zip(self.pairs, self.rejected_bh, strict=True) if r]
        return sorted(keep, key=lambda p: p.eg.p_value)

    def both_tests(self) -> list[PairResult]:
        """BH survivors that Johansen also rejects — the strictest reading."""
        return [p for p in self.survivors() if p.joh is not None and p.joh.rejects_no_cointegration]

    def summary(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "pairs_tested": self.tested,
            "alpha": self.alpha,
            "raw_hits_engle_granger": self.raw_hits,
            "expected_false_positives_by_chance": round(self.expected_false_positives, 1),
            "bh_corrected_hits": self.corrected_hits,
            "johansen_hits_uncorrected": self.johansen_hits,
            "hits_both_tests": len(self.both_tests()),
            "skipped_pairs": len(self.skipped),
            "fdr_method": FDR_METHOD,
        }


def screen(
    matrix: PriceMatrix,
    lo: int,
    hi: int,
    alpha: float = ALPHA,
    min_overlap: int = MIN_OVERLAP,
    window_label: str = "",
) -> ScreenResult:
    """Test every symbol pair over bars ``[lo, hi)`` of ``matrix``.

    Orientation is fixed by sorted symbol order so the same pair is never
    tested twice under two names. Tests run on **log** closes: cointegration in
    logs is the form corresponding to a stable ratio between the assets, which
    is the thing a hedge ratio can actually hold.
    """
    result = ScreenResult(alpha=alpha, window=window_label)
    for left, right in combinations(matrix.symbols, 2):
        a = matrix.column(left)[lo:hi]
        b = matrix.column(right)[lo:hi]
        keep = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
        overlap = int(keep.sum())
        if overlap < min_overlap:
            result.skipped[f"{left}/{right}"] = f"{overlap} overlapping bars < {min_overlap}"
            continue
        y, x = np.log(a[keep]), np.log(b[keep])
        eg = engle_granger(left, right, y, x)
        if eg is None:
            result.skipped[f"{left}/{right}"] = "too few observations for the test"
            continue
        result.pairs.append(
            PairResult(left=left, right=right, eg=eg, joh=johansen(left, right, y, x))
        )

    p_values = [p.eg.p_value for p in result.pairs]
    if p_values:
        rejected, q_values, _, _ = multipletests(p_values, alpha=alpha, method=FDR_METHOD)
        result.rejected_bh = [bool(r) for r in rejected]
        result.q_values = [float(q) for q in q_values]
    return result


def persistence(formation: ScreenResult, holdout: ScreenResult) -> dict[str, Any]:
    """How many formation-window relationships still hold out of sample.

    The literature's recurring finding is that cointegrating vectors are
    time-varying rather than static. If that holds here it shows up as a
    survival rate barely above what re-testing an arbitrary subset would give,
    so that base rate is reported alongside: "40% persisted" means nothing
    without knowing that 38% of *all* pairs pass in the second window anyway.
    """
    survived_keys = {p.key for p in formation.survivors()}
    holdout_keys = {p.key for p in holdout.pairs}
    holdout_raw = {p.key for p in holdout.pairs if p.eg.p_value < holdout.alpha}
    holdout_bh = {p.key for p in holdout.survivors()}
    retested = sorted(survived_keys & holdout_keys)
    still_raw = [k for k in retested if k in holdout_raw]
    still_bh = [k for k in retested if k in holdout_bh]
    base_rate = len(holdout_raw) / holdout.tested if holdout.tested else 0.0
    rate = len(still_raw) / len(retested) if retested else None
    return {
        "formation_survivors": len(survived_keys),
        "retestable_in_holdout": len(retested),
        "persisted_uncorrected": len(still_raw),
        "persisted_bh": len(still_bh),
        "persistence_rate_uncorrected": round(rate, 4) if rate is not None else None,
        "holdout_base_rate_any_pair": round(base_rate, 4),
        "lift_over_base_rate": (
            round(rate / base_rate, 3) if rate is not None and base_rate > 0 else None
        ),
    }
