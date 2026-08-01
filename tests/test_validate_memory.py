"""Memory regression guard: validation must process a large day in bounded RSS.

The 2026-07-31 full-day validation was OOM-killed at 12.8 GB RSS because the
replay retained every emitted snapshot row in memory before writing. The
validator had only ever been exercised on a 25-second fixture, three orders of
magnitude below a real day — exactly the gap this test closes. It generates a
synthetic venue-day large enough to force multiple streaming flushes, replays
it through the real ``validate_venue_day`` in a subprocess, and asserts the
subprocess's peak RSS stays under a fixed ceiling. Unbounded row retention at
this scale costs well over 1 GB and fails the ceiling; the streaming path
stays comfortably below it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import orjson
import pyarrow.parquet as pq

from data.config import REPO_ROOT
from data.recorder.writer import RawFileWriter
from data.store import book_partition_dir

DATE = "2026-07-30"
# 2026-07-30T12:00:00Z — every synthetic message lands inside DATE.
BASE_NS = 1_785_412_800 * 1_000_000_000
MSG_SPACING_NS = 3_000_000  # 3 ms between messages ≈ 25 minutes of feed
SYMBOL = "BTC-USD"
DEPTH = 10

# Large enough that retaining every row in memory (~2.3 KB per emitted row,
# measured on real 2026-07-31 data) exceeds 1 GB, while the streaming path
# stays under the ceiling with wide margin.
N_MESSAGES = 400_000
PEAK_RSS_CEILING_MB = 600

# Runs inside the subprocess so ru_maxrss measures the validation alone, not
# the pytest process. Prints machine-readable lines the test parses.
DRIVER = """
import resource
import sys
from pathlib import Path

from data.config import AppConfig, load_config
from data.validate.replay import validate_venue_day

data_root = Path(sys.argv[1])
cfg = AppConfig(data_root=data_root, logs_dir=data_root / "logs", venues=load_config().venues)
report = validate_venue_day(cfg, "coinbase", sys.argv[2])

print(f"PEAK_RSS_KB={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}")
print(f"MSGS={report.msgs_total}")
print(f"ROWS={sum(s.rows_written for s in report.symbols)}")
print(f"SEQ_GAPS={sum(s.seq_gaps or 0 for s in report.symbols)}")
print(f"CROSSED={sum(s.crossed_total for s in report.symbols)}")
"""


def _snapshot_message() -> dict[str, object]:
    updates = [
        {"side": "bid", "price_level": f"{50_000 - i}.0", "new_quantity": "1.0"}
        for i in range(DEPTH)
    ] + [
        {"side": "offer", "price_level": f"{50_001 + i}.0", "new_quantity": "1.0"}
        for i in range(DEPTH)
    ]
    return {
        "channel": "l2_data",
        "sequence_num": 0,
        "events": [{"type": "snapshot", "product_id": SYMBOL, "updates": updates}],
    }


def _update_message(seq: int) -> dict[str, object]:
    """One-level qty change that never removes a level and never crosses."""
    if seq % 2 == 0:
        side, price = "bid", 50_000 - (seq % 5)
    else:
        side, price = "offer", 50_001 + (seq % 5)
    update = {
        "side": side,
        "price_level": f"{price}.0",
        "new_quantity": f"{1 + (seq % 3)}.0",
    }
    return {
        "channel": "l2_data",
        "sequence_num": seq,
        "events": [{"type": "update", "product_id": SYMBOL, "updates": [update]}],
    }


def _generate_day(raw_dir: Path) -> None:
    writer = RawFileWriter(raw_dir, "coinbase")
    try:
        writer.write(BASE_NS, orjson.dumps(_snapshot_message()).decode())
        for seq in range(1, N_MESSAGES):
            writer.write(
                BASE_NS + seq * MSG_SPACING_NS, orjson.dumps(_update_message(seq)).decode()
            )
    finally:
        writer.close()


def test_validation_peak_rss_is_bounded_on_a_large_day(tmp_path: Path) -> None:
    # Arrange: a synthetic sequence-contiguous coinbase day, big enough that
    # retaining rows in memory would blow the ceiling several times over.
    _generate_day(tmp_path / "raw")

    # Act: validate in a subprocess so peak RSS is attributable to this run.
    result = subprocess.run(
        [sys.executable, "-c", DRIVER, str(tmp_path), DATE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    # Assert: completed, processed everything, and stayed under the ceiling.
    assert result.returncode == 0, f"validation subprocess failed:\n{result.stderr[-2000:]}"
    values = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line and line.split("=", 1)[0].isupper()
    )
    assert int(values["MSGS"]) == N_MESSAGES
    assert int(values["SEQ_GAPS"]) == 0, "synthetic day is sequence-contiguous by construction"
    assert int(values["CROSSED"]) == 0, "synthetic updates never cross the book"

    rows_written = int(values["ROWS"])
    assert rows_written >= N_MESSAGES, "every l2 message must emit at least its event row"

    # The streamed parquet output must be complete and ordered, not just small.
    part = book_partition_dir(tmp_path / "processed", "coinbase", SYMBOL, DATE)
    table = pq.read_table(part / "part-000.parquet")
    assert table.num_rows == rows_written
    ts = table.column("ts_ns").to_pylist()
    assert ts == sorted(ts)

    peak_mb = int(values["PEAK_RSS_KB"]) / 1024
    assert peak_mb < PEAK_RSS_CEILING_MB, (
        f"validation peaked at {peak_mb:.0f} MB RSS for {N_MESSAGES:,} messages "
        f"(ceiling {PEAK_RSS_CEILING_MB} MB) — the replay path is retaining "
        "per-message state instead of streaming"
    )
