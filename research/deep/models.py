"""Two small models and the windowing that feeds the sequential one.

Deliberately plain: an MLP over the same 42 features the trees see, and a
single-layer GRU over a short window of those feature vectors. No attention, no
convolutional stack, no residual tower — the published limit-order-book
architectures that motivate those choices do not generalise across market
conditions, and this project has days of one regime.

**The windowing is where a sequential model leaks**, so it is written to make
that impossible rather than unlikely. :func:`make_windows` builds row ``i`` from
rows ``[i - L + 1 .. i]`` inclusive — the sample's own bar and the ``L-1``
before it, never the one after. The label for row ``i`` resolves at ``i``'s
timestamp plus the horizon, strictly later than every row in its window.
:func:`window_contains_only_past` states exactly that, and ``tests/test_deep.py``
checks it against a planted future value.

Standardisation is fitted on the **training fold only** and applied to the test
fold. Fitting a scaler over the whole array before splitting is the most common
quiet leak in a deep-learning pipeline: it is not a label leak, so nothing
raises, and the test fold has still seen the training distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from torch import nn

from research.validation.purged_kfold import PurgedKFold

NS_PER_MS = 1_000_000


@dataclass(frozen=True)
class DeepConfig:
    """Everything the training run assumes, in one place.

    These are "enough to train stably" values, not searched ones. The task
    forbids a search and the reason is in the package docstring.
    """

    hidden: int = 64
    layers: int = 2
    window: int = 16
    epochs: int = 6
    batch_size: int = 1024
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    dropout: float = 0.1
    seed: int = 17
    max_train_rows: int = 400_000

    def describe(self) -> dict[str, Any]:
        return {
            "hidden": self.hidden,
            "layers": self.layers,
            "window_bars": self.window,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "dropout": self.dropout,
            "seed": self.seed,
            "max_train_rows": self.max_train_rows,
            "search": "none — fixed values chosen to train stably, never tuned on results",
        }


class MLP(nn.Module):
    """Plain feed-forward net over one bar's features."""

    def __init__(self, n_features: int, cfg: DeepConfig) -> None:
        super().__init__()
        blocks: list[nn.Module] = []
        width = n_features
        for _ in range(cfg.layers):
            blocks += [nn.Linear(width, cfg.hidden), nn.ReLU(), nn.Dropout(cfg.dropout)]
            width = cfg.hidden
        blocks.append(nn.Linear(width, 1))
        self.net = nn.Sequential(*blocks)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Accept a window and use only its final bar, so both architectures
        # share one training loop without a branch at every call site.
        if x.dim() == 3:
            x = x[:, -1, :]
        out: torch.Tensor = self.net(x)
        return out.squeeze(-1)


class GRUClassifier(nn.Module):
    """One recurrent layer over a short window, then a linear head."""

    def __init__(self, n_features: int, cfg: DeepConfig) -> None:
        super().__init__()
        self.gru = nn.GRU(
            input_size=n_features, hidden_size=cfg.hidden, num_layers=1, batch_first=True
        )
        self.drop = nn.Dropout(cfg.dropout)
        self.head = nn.Linear(cfg.hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 2:
            x = x.unsqueeze(1)
        sequence, _ = self.gru(x)
        # The final step is the sample's own bar; earlier steps are its past.
        out: torch.Tensor = self.head(self.drop(sequence[:, -1, :]))
        return out.squeeze(-1)


def make_windows(features: NDArray[np.float64], length: int) -> NDArray[np.float32]:
    """Row ``i`` becomes the ``length`` bars ending at ``i``, inclusive.

    Rows before the window is full repeat the earliest available bar, which is
    padding on the *past* side. Padding on the future side would be exactly the
    leak this module is arranged to prevent.
    """
    n, k = features.shape
    out = np.empty((n, length, k), dtype=np.float32)
    for offset in range(length):
        lag = length - 1 - offset
        idx = np.maximum(np.arange(n) - lag, 0)
        out[:, offset, :] = features[idx]
    return out


def window_contains_only_past(length: int, index: int) -> list[int]:
    """The source rows :func:`make_windows` reads for ``index``; never above it."""
    return [max(index - (length - 1 - offset), 0) for offset in range(length)]


def _standardise(
    train: NDArray[np.float32], test: NDArray[np.float32]
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Fit on train, apply to both. Fitting on all rows is a quiet leak."""
    flat = train.reshape(-1, train.shape[-1])
    mean = np.nanmean(flat, axis=0)
    std = np.nanstd(flat, axis=0)
    std[~np.isfinite(std) | (std == 0.0)] = 1.0
    mean[~np.isfinite(mean)] = 0.0

    def apply(block: NDArray[np.float32]) -> NDArray[np.float32]:
        scaled = (np.nan_to_num(block, nan=0.0, posinf=0.0, neginf=0.0) - mean) / std
        return np.asarray(scaled, dtype=np.float32)

    return apply(train), apply(test)


def train_predict(
    model: nn.Module,
    x_train: NDArray[np.float32],
    y_train: NDArray[np.int64],
    x_test: NDArray[np.float32],
    cfg: DeepConfig,
) -> NDArray[np.float64]:
    """Fit one model on one fold and return its test-fold probabilities."""
    torch.manual_seed(cfg.seed)
    optimiser = torch.optim.AdamW(
        model.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay
    )
    loss_fn = nn.BCEWithLogitsLoss()

    # A declared cap on training rows rather than a silent one: 14 GiB of RAM
    # and a CPU-only build, and ADR-025's rule that a bound on the experiment is
    # part of the experiment. Rows come from the END of the training block — the
    # most recent data — never sampled at random across it.
    if x_train.shape[0] > cfg.max_train_rows:
        x_train = x_train[-cfg.max_train_rows :]
        y_train = y_train[-cfg.max_train_rows :]

    xt = torch.from_numpy(np.ascontiguousarray(x_train))
    yt = torch.from_numpy(y_train.astype(np.float32))
    model.train()
    for _ in range(cfg.epochs):
        order = torch.randperm(xt.shape[0])
        for start in range(0, xt.shape[0], cfg.batch_size):
            idx = order[start : start + cfg.batch_size]
            optimiser.zero_grad()
            loss_fn(model(xt[idx]), yt[idx]).backward()
            optimiser.step()

    model.eval()
    outputs: list[NDArray[np.float64]] = []
    with torch.no_grad():
        xs = torch.from_numpy(np.ascontiguousarray(x_test))
        for start in range(0, xs.shape[0], cfg.batch_size):
            logits = model(xs[start : start + cfg.batch_size])
            outputs.append(torch.sigmoid(logits).numpy().astype(np.float64))
    return np.concatenate(outputs) if outputs else np.empty(0, dtype=np.float64)


def fit_oof(
    kind: str,
    ts_ns: NDArray[np.int64],
    features: NDArray[np.float64],
    y01: NDArray[np.int64],
    horizon_ms: int,
    n_splits: int,
    embargo_ns: int,
    cfg: DeepConfig | None = None,
) -> NDArray[np.float64]:
    """Out-of-fold probabilities under the *same* purged CV the baseline uses.

    Identical folds are the whole point. A deep model evaluated under a
    different split is not comparable to the tree it is meant to beat, and the
    pre-registered margin would then be measuring the split.
    """
    conf = cfg or DeepConfig()
    windows = make_windows(features, conf.window if kind == "gru" else 1)
    prob = np.full(y01.size, np.nan)
    for train_idx, test_idx in PurgedKFold(
        n_splits, horizon_ms * NS_PER_MS, embargo_ns=embargo_ns
    ).split(ts_ns.tolist()):
        if len(set(y01[train_idx].tolist())) < 2:
            continue
        x_train, x_test = _standardise(windows[train_idx], windows[test_idx])
        model: nn.Module = (
            GRUClassifier(features.shape[1], conf)
            if kind == "gru"
            else MLP(features.shape[1], conf)
        )
        prob[test_idx] = train_predict(model, x_train, y01[train_idx], x_test, conf)
    return prob
