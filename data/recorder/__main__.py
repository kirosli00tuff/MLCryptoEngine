"""CLI: ``python -m data.recorder [--venue kraken] [--dry-run]`` (see ``make record``)."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from collections.abc import Coroutine
from typing import Any

from data.recorder.service import run_service


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m data.recorder",
        description="Record public order book and trade feeds to raw NDJSON (zstd).",
    )
    parser.add_argument(
        "--venue",
        action="append",
        dest="venues",
        metavar="KEY",
        help="venue key from config/venues.yaml (repeatable; default: all supported)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="connect, print the first configured number of raw messages, and exit",
    )
    return parser.parse_args(argv)


def _run(coro: Coroutine[Any, Any, None]) -> None:
    try:
        import uvloop
    except ImportError:  # pragma: no cover - uvloop is a core dependency on Linux
        asyncio.run(coro)
        return
    uvloop.run(coro)


def main() -> None:
    args = _parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        _run(run_service(args.venues, args.dry_run))


if __name__ == "__main__":
    main()
