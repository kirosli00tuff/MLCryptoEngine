"""Memory regression guard for the research pipeline, at realistic scale.

Both Phase A defects that reached production were found only at full scale
(the validator OOM, the cold-start bug), so the research extraction path gets
the same guard the validator got: a synthetic day large enough to force many
streaming flushes and label resolutions, run in a subprocess, with peak RSS
asserted under a fixed ceiling. Retaining per-event state (or buffering the
whole day's samples) fails this test; the streaming design passes with wide
margin.
"""

from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

from data.config import REPO_ROOT
from data.store import BookDayWriter, TradesDayWriter
from tests.test_leakage import _book_row

DATE = "2026-07-30"
BASE_NS = 1_785_412_800 * 1_000_000_000
NS_PER_MS = 1_000_000
VENUE = "kraken"
SYMBOL = "BTC/USD"
N_BOOK_EVENTS = 400_000
PEAK_RSS_CEILING_MB = 900  # imports alone (numpy/pyarrow/lightgbm chain) cost ~350 MB

DRIVER = """
import resource
import sys
from pathlib import Path

from data.config import AppConfig, load_config
from research.pipeline import extract_samples

root = Path(sys.argv[1])
cfg = AppConfig(data_root=root, logs_dir=root / "logs", venues=load_config().venues)
path = extract_samples(cfg, sys.argv[2], sys.argv[3], sys.argv[4])
print(f"PATH={path}")
print(f"PEAK_RSS_KB={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}")
"""


def test_pending_samples_buffer_is_capped_when_labels_never_resolve(tmp_path: Path) -> None:
    """A stalled label stream must not buffer the day: past the cap, the
    oldest sample flushes censored instead of waiting forever."""
    import pyarrow.parquet as pq

    from data.store import StreamingPartWriter
    from research.pipeline import _PendingSamples, _samples_schema

    writer = StreamingPartWriter(tmp_path / "part-000.parquet", _samples_schema(), flush_rows=10)
    pending = _PendingSamples(writer, resolutions_needed=5, max_pending=10)
    template = dict.fromkeys(_samples_schema().names)
    for i in range(50):
        pending.add(i, {**template, "ts_ns": BASE_NS + i, "valid": True}, tb_armed=False)
        assert len(pending._rows) <= 11, "buffer must stay capped"

    pending.finalize()
    path = writer.close()
    assert path is not None
    table = pq.read_table(path)
    assert table.num_rows == 50, "every sample is written exactly once, censored or not"
    ts = table.column("ts_ns").to_pylist()
    assert ts == sorted(ts), "force-flushing must preserve timestamp order"


def test_sample_extraction_peak_rss_is_bounded_at_scale(tmp_path: Path) -> None:
    # Arrange: a 400k-event random-walk day in the processed layout.
    rng = random.Random(3)
    books = BookDayWriter(tmp_path / "processed", VENUE, SYMBOL, DATE)
    trades = TradesDayWriter(tmp_path / "processed", VENUE, SYMBOL, DATE)
    mid = 50_000.0
    for i in range(N_BOOK_EVENTS):
        ts = BASE_NS + i * 10 * NS_PER_MS
        mid += rng.choice((-1.0, 0.0, 1.0))
        books.append([_book_row(ts, mid, rng)])
        if i % 5 == 0:
            trades.append(
                [
                    {
                        "venue": VENUE,
                        "symbol": SYMBOL,
                        "ts_ns": ts + 1,
                        "exchange_ns": ts,
                        "price": mid,
                        "qty": rng.uniform(0.001, 0.5),
                        "venue_side": rng.choice(("buy", "sell")),
                        "trade_id": str(i),
                    }
                ]
            )
    books.close()
    trades.close()

    # Act: extract in a subprocess so peak RSS is attributable to this run.
    result = subprocess.run(
        [sys.executable, "-c", DRIVER, str(tmp_path), VENUE, SYMBOL, DATE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    # Assert
    assert result.returncode == 0, f"extraction failed:\n{result.stderr[-2000:]}"
    values = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if line.startswith(("PATH", "PEAK"))
    )
    assert values["PATH"] != "None", "extraction must produce a samples parquet"
    peak_mb = int(values["PEAK_RSS_KB"]) / 1024
    assert peak_mb < PEAK_RSS_CEILING_MB, (
        f"sample extraction peaked at {peak_mb:.0f} MB RSS for {N_BOOK_EVENTS:,} events "
        f"(ceiling {PEAK_RSS_CEILING_MB} MB) — something is retaining per-event state"
    )
