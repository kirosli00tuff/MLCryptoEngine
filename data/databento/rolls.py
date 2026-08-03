"""Roll boundaries for continuous futures series, derived from symbology.

A continuous series (``MBT.c.0``) is a splice: on one date it maps to one
instrument, on the next to another. The price series therefore carries a
discontinuity at each roll that is a *contract change*, not a market move.
A feature lookback or label horizon spanning that point mixes two
instruments and produces a return that never happened.

**Derived, never detected.** The vendor's symbology API states exactly which
instrument the continuous series maps to over each date interval, so a roll
is a known fact with a known timestamp. The alternative — inferring rolls
from price jumps — would fire on genuine market moves and miss quiet rolls,
turning a bookkeeping fact into a detection problem with two failure modes.

A roll is an interval, not an instant: the unsafe region extends backward by
the longest feature lookback and forward by the longest label horizon,
because a window touching the boundary from either side spans both
contracts. Both come from the configured values, not constants, so extending
the horizon set automatically widens the exclusion (the same discipline as
the embargo in ADR-015).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson

from data.config import AppConfig
from data.recorder.gaps import merge_windows

NS_PER_S = 1_000_000_000
ROLLS_SUBDIR = Path("vendor") / "databento" / "rolls"


@dataclass(frozen=True, slots=True)
class RollBoundary:
    """One instrument change in a continuous series."""

    symbol: str
    date: str  # first UTC date on which the NEW instrument applies
    ts_ns: int  # midnight UTC of that date — the splice point
    from_instrument: str
    to_instrument: str


def rolls_path(cfg: AppConfig, symbol: str) -> Path:
    return cfg.data_root / ROLLS_SUBDIR / f"{symbol.replace('.', '_')}.jsonl"


def _date_to_ns(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()) * NS_PER_S


def resolve_rolls(
    cfg: AppConfig, symbol: str, start_date: str, end_date: str, dataset: str = "GLBX.MDP3"
) -> list[RollBoundary]:
    """Roll boundaries for ``symbol`` over ``[start_date, end_date)``.

    Metadata-only: symbology resolution costs nothing, so this never touches
    the spend gate.
    """
    import databento  # lazy

    client = databento.Historical(cfg.require_databento_key())
    response = client.symbology.resolve(
        dataset=dataset,
        symbols=[symbol],
        stype_in="continuous",
        stype_out="instrument_id",
        start_date=start_date,
        end_date=end_date,
    )
    intervals = sorted(response["result"].get(symbol, []), key=lambda e: str(e["d0"]))
    boundaries: list[RollBoundary] = []
    for previous, current in zip(intervals, intervals[1:], strict=False):
        if str(previous["s"]) == str(current["s"]):
            continue  # contiguous intervals, same instrument: not a roll
        boundaries.append(
            RollBoundary(
                symbol=symbol,
                date=str(current["d0"]),
                ts_ns=_date_to_ns(str(current["d0"])),
                from_instrument=str(previous["s"]),
                to_instrument=str(current["s"]),
            )
        )
    return boundaries


def write_rolls(cfg: AppConfig, symbol: str, boundaries: list[RollBoundary]) -> Path:
    """Persist boundaries alongside the data so they survive into every run."""
    path = rolls_path(cfg, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        for boundary in sorted(boundaries, key=lambda b: b.ts_ns):
            fh.write(orjson.dumps(asdict(boundary)) + b"\n")
    return path


def read_rolls(cfg: AppConfig, symbol: str) -> list[RollBoundary]:
    """Stored boundaries, oldest first. Missing file means none recorded."""
    path = rolls_path(cfg, symbol)
    if not path.is_file():
        return []
    out: list[RollBoundary] = []
    with path.open("rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                out.append(RollBoundary(**orjson.loads(stripped)))
    return out


def roll_windows_ns(
    boundaries: list[RollBoundary], lookback_ns: int, horizon_ns: int
) -> list[tuple[int, int]]:
    """Unsafe *sample times* around each roll, unioned.

    Derivation, because the intuitive answer is the wrong way round. A sample
    at ``t`` reads data over ``[t - lookback, t + horizon]``. It is unsafe iff
    that span contains the roll instant ``R``:

        t - lookback < R <= t + horizon   <=>   R - horizon <= t < R + lookback

    So the exclusion window on sample time runs **backward by the label
    horizon and forward by the feature lookback** — the opposite of the
    natural reading. A label window is what reaches forward across the
    splice, so it is samples *before* the roll that are mostly at risk; the
    lookback only endangers samples just after it.

    Unioned per the CLAUDE.md interval rule: monthly rolls with a wide
    horizon can produce overlapping windows, and summing them would
    double-count excluded time.
    """
    if lookback_ns < 0 or horizon_ns < 0:
        raise ValueError("lookback and horizon must be non-negative")
    return merge_windows((b.ts_ns - horizon_ns, b.ts_ns + lookback_ns) for b in boundaries)
