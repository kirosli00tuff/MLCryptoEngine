"""Stage C.17: medium-horizon prediction on untested feature classes.

The final research door, and registered as such. Every model this project
trained consumed microstructure features at horizons of 100 ms to 15 minutes,
and every closure was cost-bound or signal-absent. The one closure the external
audit called feature-limited rather than cost-proven is days-to-weeks
prediction — where weekly turnover makes cost structurally irrelevant — using
information classes no model here has seen: stablecoin flows, exchange
netflows, funding-regime state, basis state.

The prior is failure and the stakes are stated in advance: **if this stage
fails its registered bars (progress.md, commit 370ba41), the alpha search of
this project ends by decision.** That sentence was committed before any data
was probed.

The correctness rule that owns this stage is **publication lag**. A daily
on-chain metric dated day T is not knowable during day T — it exists only
after the day closes plus the provider's computation delay, and providers
revise. Every feature carries a registered lag (``usable_at = metric_date +
lag``), the walk-forward may only read features whose ``usable_at`` precedes
the decision, and the planted-future canary plus prefix-invariance probes run
against this pipeline at daily cadence. Medium-horizon on-chain backtests
classically lie exactly here, which is why the discipline is the centre of the
design rather than a footnote.
"""
