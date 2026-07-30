"""CLI: ``python -m ops.telemetry`` (see ``make telemetry``)."""

from __future__ import annotations

import asyncio
import contextlib

from ops.telemetry.service import run_service


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_service())


if __name__ == "__main__":
    main()
