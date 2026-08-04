"""Append-only provenance record for every downloaded archive file.

Free data is still data with a provenance problem: a bar file on disk with no
record of where it came from or when cannot later be distinguished from one
that was patched by hand, re-downloaded after the source silently revised it,
or copied in from somewhere else entirely. Vendor purchases already carry this
discipline (ADR-022's spend ledger); free downloads get the same treatment
minus the money.

One line per file, written *after* the bytes land and the checksum is taken, so
a manifest entry is evidence of a completed download rather than of an intent
to make one. That is the opposite of the vendor ledger's ordering, and
deliberately so: the ledger commits a charge before the request because the
charge happens whether or not the bytes arrive. Nothing is spent here, so the
entry can wait for proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson

from data.config import AppConfig

ARCHIVE_SUBDIR = Path("vendor") / "archive"
MANIFEST_NAME = "manifest.jsonl"


def archive_dir(cfg: AppConfig) -> Path:
    """Root of the immutable archive tree, alongside the vendor tree."""
    return cfg.data_root / ARCHIVE_SUBDIR


def manifest_path(cfg: AppConfig) -> Path:
    return archive_dir(cfg) / MANIFEST_NAME


@dataclass(frozen=True)
class ArchiveRecord:
    """Provenance for one downloaded file.

    ``venue`` is whose prints these are; ``source`` is which archive served
    them. They differ, and the difference matters: Binance dumps carry Binance
    prints, but the dump endpoint is a separate artefact from the exchange and
    can be revised — or stop being published — independently of it.
    """

    source: str
    venue: str
    dataset: str
    symbol: str
    interval: str
    period: str
    url: str
    path: str
    # Named size_bytes, not bytes: a field called `bytes` shadows the builtin
    # inside the class body, so the annotation on to_json() below resolves to
    # this int instead of the type.
    size_bytes: int
    sha256: str
    retrieved_at: str

    def to_json(self) -> bytes:
        return orjson.dumps(self.__dict__)


def utc_stamp() -> str:
    return datetime.now(UTC).isoformat()


def append(cfg: AppConfig, record: ArchiveRecord) -> None:
    """Append one provenance line. Creates the manifest if absent."""
    path = manifest_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        fh.write(record.to_json() + b"\n")


def read_all(cfg: AppConfig) -> list[ArchiveRecord]:
    """Every recorded download, oldest first. Missing manifest means none."""
    path = manifest_path(cfg)
    if not path.is_file():
        return []
    out: list[ArchiveRecord] = []
    with path.open("rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                out.append(ArchiveRecord(**orjson.loads(stripped)))
    return out


def already_have(target: Path) -> bool:
    """True if this exact file is already on disk with bytes in it.

    A zero-byte file counts as absent: an interrupted download must not
    masquerade as a completed one. Trusting the path to merely exist is how a
    truncated month becomes a silent hole in a price series.
    """
    return target.is_file() and target.stat().st_size > 0
