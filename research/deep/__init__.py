"""Stage C.14 Task 4: does more model capacity find what trees could not?

The register closed H2 on **absent signal** rather than on model capacity, so
more capacity is unlikely to help. This package tests that once, properly, so
the question is settled with evidence instead of argument — and so no future
session reopens it on the grounds that a neural network was never tried.

Four constraints, all from the task's own framing and all deliberate.

**The bar was written before training.** progress.md, commit a2d7466: a deep
model must beat the LightGBM baseline at 900 s by **>= +0.020 AUC and >= +1.00
bps of gross capture**, out of sample, under the same purged CV and embargo.
Both, not either. An AUC win without a capture win is a failure, and it is the
specific failure Task 1's premise predicts, because AUC is magnitude-blind.

**Two architectures, not a survey.** An MLP and one sequential model. The
literature on limit-order-book deep learning finds elaborate architectures fail
to generalise across market conditions, and that a plain MLP beats several
published designs; a survey here would buy variance rather than knowledge.

**No hyperparameter search beyond training stably.** Searching over a pipeline
this project has never validated for deep learning finds the leak, not the edge.

**Leakage is assumed until disproved.** A sequential model consuming a window of
past bars is far more exposed to off-by-one leakage than a tabular one — one
misaligned index and the window contains its own label. The planted-future-value
and prefix-invariance probes therefore run against this path specifically, and
**any improvement that fails them is reported as a leak, not a discovery**,
whatever its size.

Runs under ``.venv-dl`` (CPU-only torch). The live recorders execute from
``.venv``, which this package never touches.
"""
