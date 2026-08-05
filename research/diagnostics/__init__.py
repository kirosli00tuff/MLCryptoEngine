"""Stage C.14 diagnostics: why two closed hypotheses failed, and differently.

H1 and H2 were filed under one heading and failed in different ways. On crypto
spot AUC reached 0.941 at 100 ms against roughly 0.03 bps of gross capture —
real discrimination that could never pay 80 bps. On CME MBT AUC was 0.501 at
900 s, a coin flip. One is cost-dominated, the other signal-absent, and they
need different diagnoses.

Nothing here tries to rescue either. The expected outcome is confirming both
closures with better explanations than currently exist, and these modules are
written to make that outcome as easy to report as any other.

The governing oddity is that **classification metrics are magnitude-blind**. A
model can call the sign of a move correctly almost every time and still capture
nothing, if the moves it calls correctly are the ones near zero.
:mod:`research.diagnostics.confidence` is the test of exactly that, and its
thresholds were written into progress.md before it was ever run.
"""
