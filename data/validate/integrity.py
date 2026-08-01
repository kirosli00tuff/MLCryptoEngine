"""Which integrity mechanism scores a venue-day, and whether it actually ran.

Venues do not agree on how they let you prove a reconstructed book is correct.
Coinbase Advanced Trade stamps every envelope with ``sequence_num``, so
continuity of that counter detects dropped messages. Kraken WS v2 provides no
sequence number at all (recorder heartbeats show ``last_seq: null``) and
instead attaches a CRC32 checksum of the top 10 levels to every book update.
Neither venue offers both.

The asymmetry is a reporting hazard. A check that never ran produces a zero
failure count, and a zero failure count reads exactly like a clean check. This
module keeps the two apart: a mechanism that does not apply to a venue is
``None`` (rendered "n/a"), never ``0``, and every applicable mechanism reports
how many comparisons it actually performed alongside how many failed. Zero
failures out of zero comparisons is evidence of absence, not of integrity, and
:func:`uncertified_reason` turns it into a failure rather than a pass.
"""

from __future__ import annotations

from pydantic import BaseModel

from data.config import VenueConfig

SEQUENCE = "envelope sequence numbers"
CHECKSUM = "CRC32 book checksums"
# For snapshot-stream venues (Hyperliquid): no sequence numbers, no checksums
# — both render n/a — and the venue is scored on the cadence of its full-book
# snapshots instead. The comparison volume is the number of snapshots applied.
SNAPSHOT_CADENCE = "snapshot cadence"


class IntegrityReport(BaseModel):
    """The integrity mechanism(s) that scored one venue-day, and their volume.

    ``None`` means the venue provides no such mechanism, and the check is
    reported as not applicable. ``0`` means the mechanism applies but performed
    no comparisons — which is a failure, not a pass.
    """

    mechanism: str
    sequence_checks: int | None = None
    checksum_checks: int | None = None
    snapshot_checks: int | None = None


def mechanisms_for(vcfg: VenueConfig) -> list[str]:
    """Integrity mechanisms this venue's feed actually provides, by config."""
    names: list[str] = []
    if vcfg.sequence_numbers:
        names.append(SEQUENCE)
    if vcfg.snapshot.checksum:
        names.append(CHECKSUM)
    if vcfg.snapshot_stream:
        names.append(SNAPSHOT_CADENCE)
    return names


def describe(mechanisms: list[str]) -> str:
    """Human-readable mechanism name for the report. Never silently empty."""
    return " + ".join(mechanisms) if mechanisms else "none available"


def uncertified_reason(venue: str, mechanisms: list[str], report: IntegrityReport) -> str | None:
    """Why this venue-day's book integrity cannot be certified, or ``None``.

    Two ways to end up uncertified, both of which would otherwise present as a
    clean scorecard: the venue provides no integrity mechanism whatsoever, or
    it declares one that ran zero comparisons (for Kraken, the realistic cause
    is a symbol missing its ``instruments`` precisions, which leaves the
    checksum function unbuilt and every update unverified).
    """
    if not mechanisms:
        return (
            f"{venue}: no integrity mechanism available — the feed provides neither "
            f"{SEQUENCE} nor {CHECKSUM}, so book integrity cannot be certified"
        )
    if report.sequence_checks == 0:
        return (
            f"{venue}: declares {SEQUENCE} but 0 were observed — a zero sequence-gap "
            "count here is evidence of absence, not of integrity"
        )
    if report.checksum_checks == 0:
        return (
            f"{venue}: declares {CHECKSUM} but 0 were verified — a zero checksum-failure "
            "count here is evidence of absence, not of integrity"
        )
    if report.snapshot_checks == 0:
        return (
            f"{venue}: declares {SNAPSHOT_CADENCE} but 0 snapshots were applied — "
            "an empty snapshot stream cannot certify anything"
        )
    return None
