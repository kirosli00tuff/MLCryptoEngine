"""Leakage suite: no feature may know the future. The most valuable tests here.

Three defenses, each catching a different failure shape:

1. **Prefix invariance** — a feature vector sampled at time ``t`` by the real
   pipeline must be *exactly* reproducible from only the events with local
   timestamp strictly before ``t``. This catches off-by-one leaks (computing
   features after applying the triggering event) that correlation tests can
   miss.
2. **Planted future value** — the synthetic day is a seeded random walk, so
   its future increments are independent of everything observable at ``t``.
   Every feature's correlation with the forward return must be
   statistically indistinguishable from zero.
3. **Canary** — a deliberately leaky pseudo-feature (the future return plus
   noise) must be flagged by the same detector, proving the test has teeth
   rather than passing vacuously.
"""

from __future__ import annotations

import math
import random

import pyarrow.parquet as pq
import pytest

from data.config import AppConfig, load_config
from data.store import BookDayWriter, TradesDayWriter
from research.features.engine import FEATURE_COLUMNS, FeatureEngine
from research.pipeline import extract_samples
from research.stream.reader import merged_stream

DATE = "2026-07-30"
BASE_NS = 1_785_412_800 * 1_000_000_000  # 2026-07-30T12:00:00Z
NS_PER_MS = 1_000_000
VENUE = "kraken"
SYMBOL = "BTC/USD"
N_BOOK_EVENTS = 120_000
EVENT_SPACING_NS = 10 * NS_PER_MS
TICK = 1.0
CORR_THRESHOLD = 0.08  # ~5 sigma at the sample counts this suite produces
MIN_POINTS_FOR_CORR = 300


def _book_row(ts_ns: int, mid: float, rng: random.Random) -> dict[str, object]:
    bid, ask = mid - TICK / 2, mid + TICK / 2
    bid_qty = rng.uniform(0.5, 5.0)
    ask_qty = rng.uniform(0.5, 5.0)
    bid_prices = [bid - i * TICK for i in range(5)]
    ask_prices = [ask + i * TICK for i in range(5)]
    bid_qtys = [bid_qty] + [rng.uniform(0.5, 5.0) for _ in range(4)]
    ask_qtys = [ask_qty] + [rng.uniform(0.5, 5.0) for _ in range(4)]
    return {
        "venue": VENUE,
        "symbol": SYMBOL,
        "ts_ns": ts_ns,
        "kind": "event",
        "valid": True,
        "crossed": False,
        "locked": False,
        "best_bid": bid,
        "bid_qty": bid_qty,
        "best_ask": ask,
        "ask_qty": ask_qty,
        "mid": mid,
        "microprice": (bid_qty * ask + ask_qty * bid) / (bid_qty + ask_qty),
        "bid_prices": bid_prices,
        "bid_qtys": bid_qtys,
        "ask_prices": ask_prices,
        "ask_qtys": ask_qtys,
        "seq": None,
    }


@pytest.fixture(scope="module")
def synthetic_day(tmp_path_factory: pytest.TempPathFactory) -> AppConfig:
    """A seeded random-walk venue-day written straight into the processed layout."""
    root = tmp_path_factory.mktemp("leakage")
    rng = random.Random(42)
    books = BookDayWriter(root / "processed", VENUE, SYMBOL, DATE)
    trades = TradesDayWriter(root / "processed", VENUE, SYMBOL, DATE)
    mid = 50_000.0
    for i in range(N_BOOK_EVENTS):
        ts = BASE_NS + i * EVENT_SPACING_NS
        mid += rng.choice((-TICK, 0.0, TICK))
        books.append([_book_row(ts, mid, rng)])
        if i % 4 == 0:
            side = rng.choice(("buy", "sell"))
            trades.append(
                [
                    {
                        "venue": VENUE,
                        "symbol": SYMBOL,
                        "ts_ns": ts + 1,
                        "exchange_ns": ts,
                        "price": mid + (TICK / 2 if side == "buy" else -TICK / 2),
                        "qty": rng.uniform(0.001, 0.5),
                        "venue_side": side,
                        "trade_id": str(i),
                    }
                ]
            )
    books.close()
    trades.close()
    return AppConfig(data_root=root, logs_dir=root / "logs", venues=load_config().venues)


@pytest.fixture(scope="module")
def samples(synthetic_day: AppConfig) -> list[dict[str, object]]:
    path = extract_samples(synthetic_day, VENUE, SYMBOL, DATE)
    assert path is not None
    rows: list[dict[str, object]] = pq.read_table(path).to_pylist()
    assert len(rows) > 1_000, "synthetic day must produce a statistically useful sample count"
    return rows


def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < MIN_POINTS_FOR_CORR:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def test_no_feature_correlates_with_planted_future_value(
    samples: list[dict[str, object]],
) -> None:
    """Random-walk future increments are unknowable at t; every feature must agree."""
    future = "ret_bps_500ms"
    offenders: dict[str, float] = {}
    checked = 0
    for feature in FEATURE_COLUMNS:
        xs: list[float] = []
        ys: list[float] = []
        for row in samples:
            x, y = row.get(feature), row.get(future)
            if isinstance(x, float) and isinstance(y, float):
                xs.append(x)
                ys.append(y)
        corr = _corr(xs, ys)
        if corr is None:
            continue  # feature unavailable on this synthetic stream (e.g. cross-venue)
        checked += 1
        if abs(corr) > CORR_THRESHOLD:
            offenders[feature] = corr
    assert checked >= 20, "the sweep must actually cover the feature library"
    assert not offenders, f"features correlate with the planted future value: {offenders}"


def test_canary_leaky_feature_is_detected(samples: list[dict[str, object]]) -> None:
    """The detector must flag a feature that IS the future — or it proves nothing."""
    rng = random.Random(7)
    xs: list[float] = []
    ys: list[float] = []
    for row in samples:
        y = row.get("ret_bps_500ms")
        if isinstance(y, float):
            leaky_feature = y + rng.gauss(0.0, 0.1)
            xs.append(leaky_feature)
            ys.append(y)
    corr = _corr(xs, ys)
    assert corr is not None
    assert abs(corr) > CORR_THRESHOLD, "detector failed to flag a deliberately leaky feature"


def test_features_are_prefix_invariant(
    synthetic_day: AppConfig, samples: list[dict[str, object]]
) -> None:
    """Feature vectors must be exactly reproducible from events strictly before t.

    Catches the off-by-one leak (applying the triggering event before
    computing features) that a correlation test can miss entirely.
    """
    valid_rows = [r for r in samples if r["valid"]]
    probes = valid_rows[:: max(1, len(valid_rows) // 5)][:5]
    assert probes, "need at least one valid sample to probe"
    for row in probes:
        ts_value = row["ts_ns"]
        assert isinstance(ts_value, int)
        t = ts_value
        engine = FeatureEngine(VENUE, SYMBOL, cross=None)
        for event in merged_stream(synthetic_day.processed_dir, VENUE, SYMBOL, DATE):
            if event.local_ns >= t:
                break
            engine.on_event(event)
        recomputed = engine.compute(t)
        for feature in FEATURE_COLUMNS:
            if feature.startswith("xv_"):
                continue  # cross-venue disabled in the probe engine
            expected = row.get(feature)
            actual = recomputed.get(feature)
            if expected is None and actual is None:
                continue
            assert isinstance(expected, float) and isinstance(actual, float), (
                f"{feature}: availability differs at t={t}: parquet={expected} probe={actual}"
            )
            # Tight tolerance, not bit equality: rolling sums prune lazily, so
            # the two engines accumulate identical terms in different orders.
            # A real off-by-one leak shifts values by many orders of magnitude
            # more than float reordering ever can.
            assert math.isclose(expected, actual, rel_tol=1e-6, abs_tol=1e-9), (
                f"{feature} not prefix-invariant at t={t}: {expected} != {actual}"
            )
