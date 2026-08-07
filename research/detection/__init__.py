"""Detection track (ADR-044): rug-pull classification, outside the alpha register.

Keyless groundwork lives here. Labels are per-mechanism (hard rug, honeypot,
honest-candidate, explicit unlabeled residual), evaluation is minority-class
precision at the real base rate, and every feature carries a provenance class —
pre-event, post-event contaminated, or unknowable without an indexer — before
any model exists (ADR-045).
"""
