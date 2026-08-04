"""Free public bar archives: downloaded history, never live capture.

Kind ``archive`` in the C.9.1 venue-kind scheme (ADR-031). Three sources are
configured, and they do different jobs:

- **Binance dumps** carry the sample. They are the only free source that
  retains delisted symbols, which is what makes a survivorship-free universe
  constructible at all (ADR-029).
- **Kraken and Coinbase REST** cross-check prices on the two venues this
  project can actually trade. Neither can carry the sample: Kraken's OHLC
  endpoint hard-caps at 720 candles, and both enumerate only live products, so
  a universe drawn from either is survivorship-biased by construction.

Raw downloads are immutable and land under ``data/vendor/archive/`` with one
provenance line each in ``manifest.jsonl``.
"""

from data.archive.manifest import ArchiveRecord, archive_dir, manifest_path
from data.archive.universe import Member, Universe

__all__ = [
    "ArchiveRecord",
    "Member",
    "Universe",
    "archive_dir",
    "manifest_path",
]
