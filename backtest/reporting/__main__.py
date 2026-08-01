"""CLI: ``python -m backtest.reporting`` — regenerate schema + TS types (make types)."""

from __future__ import annotations

import sys

from backtest.reporting.ts_export import write_generated


def main() -> int:
    ts_path, schema_path = write_generated()
    print(f"wrote {ts_path}")
    print(f"wrote {schema_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
