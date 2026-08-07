"""C.24 Task 3 leakage suite for the post-launch cutoff pipeline.

Wired before the first real behavioural feature is computed, as C.21 and C.23
did for their windows. The load-bearing guarantees: the cutoff refuses a pool
that already rugged (survivor conditioning), and no activity after the cutoff can
move any feature (the planted-future canary, here a burst dropped past X).
"""

from __future__ import annotations

import pytest

from research.detection import behavior as bh

T0 = 1_700_000_000.0
HOUR = 3600.0


def test_cutoff_end_refuses_a_label_event_at_or_before_the_cutoff() -> None:
    # A hard rug at T0+30 min is inside a 1 h cutoff: the pool is not alive at X.
    with pytest.raises(bh.CutoffLeakError, match="EXCLUDED"):
        bh.cutoff_end(T0, HOUR, T0 + 1_800)
    # An event after the cutoff is fine, and the end is exactly T0+X.
    assert bh.cutoff_end(T0, HOUR, T0 + 5_000) == T0 + HOUR
    # No label event at all (a survivor) is also fine.
    assert bh.cutoff_end(T0, HOUR, None) == T0 + HOUR


def test_no_feature_incorporates_activity_after_the_cutoff() -> None:
    # Arrange — a window of activity, then a heavy burst dropped AFTER the cutoff.
    base = [bh.Sig(T0 + 10), bh.Sig(T0 + 20), bh.Sig(T0 + 1_500, err=True)]
    burst = [bh.Sig(T0 + HOUR + i) for i in range(100)]

    # Act — features with and without the post-cutoff burst.
    clean = bh.behavioral_features(base, T0, HOUR, None)
    noisy = bh.behavioral_features(base + burst, T0, HOUR, None)

    # Assert — nothing after the cutoff moved a single feature.
    assert clean == noisy


def test_features_read_inside_the_window_only() -> None:
    # Arrange — three txs in the first minute of a 1 h window, none erroring.
    sigs = [bh.Sig(T0 + 10), bh.Sig(T0 + 20), bh.Sig(T0 + 30)]

    # Act
    f = bh.behavioral_features(sigs, T0, HOUR, None)

    # Assert — counts, rate, fading decay, spread, gaps and quiet-time are exact.
    assert f["n_tx"] == 3.0
    assert f["tx_per_min"] == pytest.approx(3 / 60)
    assert f["rate_decay"] == pytest.approx(0.25)  # (0 late + 1) / (3 early + 1)
    assert f["unique_active_minutes"] == 1.0
    assert f["max_gap_s"] == pytest.approx(10.0)
    assert f["time_since_last_at_cutoff_s"] == pytest.approx(HOUR - 30)
    assert f["err_fraction"] == 0.0


def test_empty_window_encodes_silence_not_missing() -> None:
    # Act — a pool with no activity inside the window.
    f = bh.behavioral_features([], T0, HOUR, None)

    # Assert — silence is a real state: zero txs, full-window gap and quiet-time.
    assert f["n_tx"] == 0.0
    assert f["max_gap_s"] == HOUR
    assert f["time_since_last_at_cutoff_s"] == HOUR


def test_rate_decay_below_one_flags_a_fading_pool() -> None:
    # Arrange — activity front-loaded into the first third of a 1 h window.
    early = [bh.Sig(T0 + 60 * i) for i in range(1, 6)]  # five txs in the first 5 min
    late = [bh.Sig(T0 + 2_700)]  # one tx in the last third

    # Act
    f = bh.behavioral_features(early + late, T0, HOUR, None)

    # Assert — more early than late activity drives decay strictly below 1.
    assert f["rate_decay"] < 1.0
