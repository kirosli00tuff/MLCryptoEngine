"""Helius indexer access, behind a credit gate (ADR-046).

The free tier meters credits, and launch-window history across tens of
thousands of pools is exactly the request shape that exhausts a quota
overnight. Nothing in this package sends a request without passing the gate,
and the gate's ledger is append-only on disk so the cap survives a restart —
the Databento cost-gate discipline (ADR-017/022), applied to credits instead
of dollars.
"""
