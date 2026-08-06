"""Stage C.16: time-series momentum on the C.10 daily archive.

Every closed hypothesis so far assumed mean reversion or microstructure
prediction. This tests the opposite premise — that trends persist, so recent
winners keep winning over horizons of weeks to months. Turnover is low enough
that cost is nearly irrelevant, and every bar of data is already on disk from
C.10, so the whole family closes for the price of a re-read.

Three disciplines carried in from earlier stages, because momentum is where
each of their failure modes is most inviting:

**The universe is C.10's, reused verbatim** (ADR-029). Its cached construction
— top 60 by 2021-08 quote volume out of 291 then-listed symbols, spliced series
excluded — is loaded from ``data/processed/pairs/``, and a missing cache is an
error rather than a rebuild. Reconstructing from today's listings would
reintroduce exactly the survivorship bias C.10 removed, and momentum is *more*
sensitive to it than pairs were: dead coins are disproportionately past losers,
and deleting them flatters a strategy that shorts losers.

**The grid is registered and every cell is reported** (progress.md, commit
88b69d8, before any result). Momentum has two free parameters, and twelve
specifications tried means the best cell must be deflated for twelve trials —
C.10's own estimator, reused unchanged.

**A bull-market long book is beta wearing a signal's name.** The registered
benchmark is buy-and-hold BTC on the identical window, risk-adjusted — not
zero. Alpha net of BTC beta and the up/down-market split are what distinguish
"discovered a trend signal" from "discovered that the market went up".
"""
