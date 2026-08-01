"""Phase B research layer: leakage-free feature/label pipeline over validated data.

Honest framing, load-bearing: with one to a few validated days, everything in
here is pipeline validation, not evidence of edge. Microstructure
relationships shift with volatility regime, session, and venue conditions; a
signal fitted on a single day is fitted on that day's regime. Every metric
this package produces carries that caveat in report.md, and the Phase B
research conclusion stays open until the pipeline has run over enough days to
span multiple regimes — which depends on continuous recording, not more code.
"""
