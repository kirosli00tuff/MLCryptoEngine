"""Purged k-fold cross-validation with embargo, on the local clock.

Reference: Lopez de Prado, *Advances in Financial Machine Learning* (2018),
ch. 7. Labels here span time — a sample at ``t`` with a 30 s horizon is a
function of the future window ``(t, t+30s]`` — so a plain k-fold leaks:
training samples adjacent to a test fold share label windows with it. Two
defenses, both structural: **purging** drops any training sample whose label
window overlaps the test block, and an **embargo** extends the exclusion
after the test block by at least the label horizon, so serial correlation
cannot smuggle test information into training either.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence


class PurgedKFold:
    """Contiguous time-block folds with purge + embargo around each test block."""

    def __init__(
        self,
        n_splits: int,
        label_horizon_ns: int,
        embargo_ns: int | None = None,
    ) -> None:
        if n_splits < 2:
            raise ValueError("n_splits must be at least 2")
        if label_horizon_ns < 0:
            raise ValueError("label_horizon_ns must be non-negative")
        self._n_splits = n_splits
        self._horizon_ns = label_horizon_ns
        # Embargo defaults to the label horizon — the minimum that prevents an
        # overlapping-label leak; larger values also damp serial correlation.
        self._embargo_ns = embargo_ns if embargo_ns is not None else label_horizon_ns

    def split(self, ts_ns: Sequence[int]) -> Iterator[tuple[list[int], list[int]]]:
        """Yield (train_indices, test_indices); ``ts_ns`` must be sorted ascending."""
        n = len(ts_ns)
        if n < self._n_splits:
            raise ValueError(f"{n} samples cannot form {self._n_splits} folds")
        if any(ts_ns[i] > ts_ns[i + 1] for i in range(n - 1)):
            raise ValueError("sample timestamps must be sorted ascending")
        fold_size = n // self._n_splits
        for fold in range(self._n_splits):
            lo = fold * fold_size
            hi = n if fold == self._n_splits - 1 else (fold + 1) * fold_size
            test_start_ns = ts_ns[lo]
            test_end_ns = ts_ns[hi - 1] + self._horizon_ns  # last test label window end
            train: list[int] = []
            for i in range(n):
                if lo <= i < hi:
                    continue
                # Purge: the training sample's label window [t, t+h] must not
                # overlap the test block; embargo extends the exclusion zone
                # after the test block's label windows end.
                sample_end_ns = ts_ns[i] + self._horizon_ns
                if sample_end_ns >= test_start_ns and ts_ns[i] <= test_end_ns + self._embargo_ns:
                    continue
                train.append(i)
            yield train, list(range(lo, hi))
