"""CLI: ``python -m data.trades [--venue kraken] [--date 2026-07-31]``."""

from __future__ import annotations

import argparse
import sys

from data.config import load_config
from data.recorder.reader import available_dates
from data.trades.extract import extract_trades_day
from data.trades.parse import PARSERS


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m data.trades",
        description="Extract executed trades from raw capture into processed Parquet.",
    )
    parser.add_argument("--venue", action="append", dest="venues", metavar="KEY")
    parser.add_argument("--date", action="append", dest="dates", metavar="YYYY-MM-DD")
    args = parser.parse_args()

    cfg = load_config()
    venues = args.venues if args.venues else sorted(PARSERS)
    ran = False
    for venue in venues:
        dates = args.dates if args.dates else available_dates(cfg.raw_dir, venue)
        for date in dates:
            print(f"extracting trades {venue} {date} ...", flush=True)
            written = extract_trades_day(cfg, venue, date)
            ran = True
            for symbol, rows in written.items():
                print(f"  {symbol}: {rows:,} trades", flush=True)
    if not ran:
        print("nothing to extract — record data first")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
