"""Per-creator history features under a strict T0-prefix rule (ADR-050).

The repeat offender is usually the most predictive signal in a fraud domain,
and it is also the one most exposed to look-ahead: a creator's rug rate over
their *full* history includes launches that happened after the pool being
scored. Every function here therefore takes the creator's launch list and a
cutoff, and reads **only launches strictly before the cutoff** — the pool being
scored and everything after it are invisible by construction, and
``tests/test_detection_creator.py`` plants a later same-creator rug and asserts
no feature moves.

Two honesty constraints, both from C.23's measurement:

- **SolRPDS has no creator field** (verified 2026-08-07 across CSV and JSON), so
  the creator address is derived per pool from the Helius launch-window fetch
  (the mint authority / first minter), not looked up. Creator *history* is thus
  bounded to the fetched sample: a creator's other launches are only visible if
  they too were fetched. ``non_first_seen_coverage`` measures how often that
  actually happens, because a feature that fires on 3% of the sample cannot
  carry a precision target — reported, never assumed.
- ``first_seen`` is a leak-free *floor*, not ground truth: it means "no prior
  launch by this creator **in the fetched set**", which over-reports first-seen
  and therefore *understates* the repeat-offender signal. Stated so the
  coverage number is read correctly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Launch:
    """One launch by a creator: its T0 and whether it met the hard-rug rule."""

    t0_s: float
    mint: str
    is_hard_rug: bool


def creator_features(history: list[Launch], mint: str, t0_s: float) -> dict[str, float]:
    """Features for ``mint`` at ``t0_s`` from a strict prefix of ``history``.

    ``history`` is every fetched launch by this creator. The prefix rule is the
    whole point: only launches with a T0 strictly before this pool's are
    admissible, so a later launch — including a later rug — can never inform an
    earlier score.
    """
    prior = [launch for launch in history if launch.t0_s < t0_s and launch.mint != mint]
    n_prior = len(prior)
    if n_prior == 0:
        return {
            "creator_prior_launches": 0.0,
            "creator_prior_hard_rugs": 0.0,
            "creator_prior_rug_rate": -1.0,  # undefined: sentinel, not 0
            "creator_days_since_prev_launch": -1.0,
            "creator_first_seen": 1.0,
        }
    n_rug = sum(1 for launch in prior if launch.is_hard_rug)
    prev_t0 = max(launch.t0_s for launch in prior)
    return {
        "creator_prior_launches": float(n_prior),
        "creator_prior_hard_rugs": float(n_rug),
        "creator_prior_rug_rate": n_rug / n_prior,
        "creator_days_since_prev_launch": (t0_s - prev_t0) / 86_400.0,
        "creator_first_seen": 0.0,
    }


def build_index(launches: list[Launch], creator_of: dict[str, str]) -> dict[str, list[Launch]]:
    """Group fetched launches by creator, so each pool can read its own history."""
    index: dict[str, list[Launch]] = {}
    for launch in launches:
        creator = creator_of.get(launch.mint)
        if creator:
            index.setdefault(creator, []).append(launch)
    return index


def non_first_seen_coverage(
    index: dict[str, list[Launch]], creator_of: dict[str, str]
) -> dict[str, float]:
    """Fraction of pools whose creator has a prior fetched launch — the gate.

    Below a few percent, the creator-history class cannot carry the bar however
    predictive it is per-firing, and that is the measured finding rather than a
    modelling choice.
    """
    total = 0
    non_first = 0
    for mint, creator in creator_of.items():
        history = index.get(creator, [])
        this = next((launch for launch in history if launch.mint == mint), None)
        total += 1
        if this is not None and any(
            launch.t0_s < this.t0_s and launch.mint != mint for launch in history
        ):
            non_first += 1
    return {
        "pools": float(total),
        "non_first_seen": float(non_first),
        "coverage": non_first / total if total else 0.0,
    }
