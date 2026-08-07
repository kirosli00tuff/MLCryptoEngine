"""C.23 creator-history tests — the prefix rule is the whole safety story.

The load-bearing test plants a later rug by the same creator and asserts that
the earlier pool's features do not move: a creator's rug rate must be computed
from a strict prefix of their history up to T0, never their full record.
"""

from __future__ import annotations

from research.detection import creator as cr


def test_creator_feature_never_sees_a_later_launch_by_the_same_creator() -> None:
    # Arrange — one prior clean launch, then the pool at T0, then a LATER rug.
    history = [
        cr.Launch(t0_s=1_000.0, mint="prior", is_hard_rug=False),
        cr.Launch(t0_s=2_000.0, mint="scored", is_hard_rug=False),
        cr.Launch(t0_s=3_000.0, mint="later_rug", is_hard_rug=True),  # the future
    ]

    # Act — features for the pool at T0=2000, with and without the future.
    out = cr.creator_features(history, "scored", 2_000.0)
    out_no_future = cr.creator_features(history[:2], "scored", 2_000.0)

    # Assert — the later rug is invisible: 1 prior launch, 0 rugs, rate 0.0,
    # and dropping the future changes nothing.
    assert out["creator_prior_launches"] == 1.0
    assert out["creator_prior_hard_rugs"] == 0.0
    assert out["creator_prior_rug_rate"] == 0.0
    assert out == out_no_future


def test_first_seen_creator_returns_undefined_rate_sentinel_not_zero() -> None:
    # Arrange — the pool is the creator's first fetched launch.
    out = cr.creator_features([cr.Launch(2_000.0, "scored", False)], "scored", 2_000.0)

    # Assert — no prior history: first_seen set, rate is the -1 sentinel (not a
    # real 0.0, which would falsely read as "a clean prior record").
    assert out["creator_first_seen"] == 1.0
    assert out["creator_prior_launches"] == 0.0
    assert out["creator_prior_rug_rate"] == -1.0


def test_prior_rug_rate_and_recency_use_only_the_prefix() -> None:
    # Arrange — three priors (2 rugs), then the scored pool, then a future rug.
    history = [
        cr.Launch(0.0, "a", True),
        cr.Launch(86_400.0, "b", True),
        cr.Launch(2 * 86_400.0, "c", False),
        cr.Launch(5 * 86_400.0, "scored", False),
        cr.Launch(9 * 86_400.0, "future", True),
    ]

    # Act
    out = cr.creator_features(history, "scored", 5 * 86_400.0)

    # Assert — 3 prior, 2 rugs → rate 2/3; recency measured to the newest PRIOR
    # (mint c at day 2), i.e. 3 days, never to the future launch.
    assert out["creator_prior_launches"] == 3.0
    assert out["creator_prior_hard_rugs"] == 2.0
    assert abs(out["creator_prior_rug_rate"] - 2 / 3) < 1e-9
    assert out["creator_days_since_prev_launch"] == 3.0


def test_coverage_counts_pools_with_a_prior_fetched_launch() -> None:
    # Arrange — creator X launches twice (pool2 has a prior), creator Y once.
    launches = [
        cr.Launch(1_000.0, "x1", True),
        cr.Launch(2_000.0, "x2", False),
        cr.Launch(1_500.0, "y1", False),
    ]
    creator_of = {"x1": "X", "x2": "X", "y1": "Y"}
    index = cr.build_index(launches, creator_of)

    # Act
    cov = cr.non_first_seen_coverage(index, creator_of)

    # Assert — only x2 has a prior fetched launch: 1 of 3.
    assert cov["pools"] == 3.0
    assert cov["non_first_seen"] == 1.0
    assert abs(cov["coverage"] - 1 / 3) < 1e-9
