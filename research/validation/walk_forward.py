"""Walk-forward splitting: rolling train window, disjoint forward test window.

Time-parameterized rather than count-parameterized, so the identical call
works on a few days of samples now and on months later — the windows just
produce more folds. Training samples whose label windows would cross the
test boundary are purged, same rationale as :mod:`purged_kfold`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

NS_PER_DAY = 86_400 * 1_000_000_000
# A defensible split for a multi-month range: six weeks to fit, two weeks to
# test. Both are chosen against the label horizon, not against the amount of
# data available — the whole point is that the data answers how many folds it
# supports, rather than the window being shrunk until it yields more.
DEFAULT_TRAIN_SPAN_NS = 42 * NS_PER_DAY
DEFAULT_TEST_SPAN_NS = 14 * NS_PER_DAY


def walk_forward_capacity(
    ts_ns: Sequence[int] | None,
    train_span_ns: int = DEFAULT_TRAIN_SPAN_NS,
    test_span_ns: int = DEFAULT_TEST_SPAN_NS,
    label_horizon_ns: int = 0,
) -> dict[str, object]:
    """How many walk-forward folds this sample span actually supports.

    Reports the count rather than adjusting the windows to reach a target.
    Shrinking a test window until the data yields three folds does not create
    three independent tests; it creates three looks at the same regime, with
    a test span small enough that the label horizon starts to dominate it.
    """
    if ts_ns is None or len(ts_ns) == 0:
        return {"folds": 0, "reason": "no samples"}
    span_ns = int(ts_ns[-1]) - int(ts_ns[0])
    folds = [
        (len(train), len(test))
        for train, test in walk_forward(ts_ns, train_span_ns, test_span_ns, None, label_horizon_ns)
    ]
    return {
        "span_days": round(span_ns / NS_PER_DAY, 2),
        "train_span_days": round(train_span_ns / NS_PER_DAY, 2),
        "test_span_days": round(test_span_ns / NS_PER_DAY, 2),
        "folds": len(folds),
        "fold_sizes": folds,
        "note": (
            "folds are counted at a fixed, horizon-appropriate window size; the "
            "window is never shrunk to manufacture more of them"
        ),
    }


def walk_forward(
    ts_ns: Sequence[int],
    train_span_ns: int,
    test_span_ns: int,
    step_ns: int | None = None,
    label_horizon_ns: int = 0,
) -> Iterator[tuple[list[int], list[int]]]:
    """Yield (train_indices, test_indices) over rolling local-clock windows.

    Windows advance by ``step_ns`` (default: the test span, giving disjoint
    consecutive test windows). A fold is only yielded when both sides are
    non-empty. ``ts_ns`` must be sorted ascending.
    """
    if train_span_ns <= 0 or test_span_ns <= 0:
        raise ValueError("train and test spans must be positive")
    n = len(ts_ns)
    if n == 0:
        return
    if any(ts_ns[i] > ts_ns[i + 1] for i in range(n - 1)):
        raise ValueError("sample timestamps must be sorted ascending")
    step = step_ns if step_ns is not None else test_span_ns
    if step <= 0:
        raise ValueError("step_ns must be positive")
    start_ns = ts_ns[0]
    end_ns = ts_ns[-1]
    window_start = start_ns
    while window_start + train_span_ns < end_ns:
        train_end = window_start + train_span_ns
        test_end = train_end + test_span_ns
        train = [
            i
            for i in range(n)
            if window_start <= ts_ns[i]
            # Purge: the label window must resolve before the test set begins.
            and ts_ns[i] + label_horizon_ns < train_end
        ]
        test = [i for i in range(n) if train_end <= ts_ns[i] < test_end]
        if train and test:
            yield train, test
        window_start += step
