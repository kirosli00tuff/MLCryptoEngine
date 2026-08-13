"""The one place the Hyperliquid fee schedule is stated (audit finding A10).

Before this module the maker fee lived as three unsourced, undated literals --
``fill_replay.MAKER_FEE_BPS``, ``inventory.MAKER_FEE_BPS`` and
``registered.ROUND_TRIP_BPS`` -- while ``config/venues.yaml`` carried fully
sourced, dated ladders for Kraken and Coinbase. Every C.27, D.1c and D.1d net
scales directly with this number, and the project's own precedent is a Kraken
schedule that was wrong for a week (ADR-055). Three independently maintained
restatements of one fact, with nothing enforcing ``ROUND_TRIP == 2 x MAKER``,
is the same exposure.

**Source.** Hyperliquid perpetuals, base tier (< $5M 14-day volume, no staking
discount): **0.015% maker / 0.045% taker** -- 1.5 bps / 4.5 bps. Recorded here
2026-08-12 from the Hyperliquid published fee schedule. This is a *documented*
figure, not a measured one: Stage 1 places no orders, so the project has no
fill of its own to reconcile it against, and the recorded ``activeAssetCtx``
stream carries no fee field. Under the project's "measured beats documented"
rule that makes it the weakest input in the chain, and it stays weakest until
D.2 or later produces a real fill to check it with.

**Scope of what is verified.** Only the base tier is used and only the base
tier is stated. Hyperliquid's ladder reaches 0 bps maker at the top; a tier
error is larger than PUMP's entire measured +4.30 bps round-trip census net, so
any non-base assumption must be re-verified before it is relied on -- the same
warning ``venues.yaml`` carries for Kraken's upper tiers.

**Rebate caveat.** Hyperliquid pays a maker *rebate* at high volume tiers. This
project quotes at the base tier, where the maker fee is a cost; a rebate tier
would flip the sign of the fee term and is out of scope for every closed stage.
"""

from __future__ import annotations

# Recorded 2026-08-12; see the module docstring for source, scope and the
# documented-not-measured caveat.
HYPERLIQUID_MAKER_BPS = 1.5
HYPERLIQUID_TAKER_BPS = 4.5
FEE_SCHEDULE_RECORDED = "2026-08-12"

# A maker round trip is two maker legs. Derived, never a second literal, so the
# two cannot drift apart the way they did before A10.
HYPERLIQUID_MAKER_ROUND_TRIP_BPS = 2.0 * HYPERLIQUID_MAKER_BPS
