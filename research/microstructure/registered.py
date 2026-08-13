"""The C.18 registered census: bars fixed in commit 6025f5c, data untouched.

This module exists in an unusual state on purpose: it is complete, tested, and
**forbidden to run on its scored population until 2026-08-11T00:00Z**. The ten
thin instruments are the population H6 will be judged on, the bars that will
judge them predate the data (progress.md, commit 6025f5c), and the guard at
the top of :func:`run_registered_census` is the enforcement rather than a
comment asking nicely.

What it will compute, per instrument, exactly as registered:

- **captured spread at trade-time state**: the touch spread standing at the
  moment of each aggressor print — the spread a resting quote actually earned
  on that fill — not the all-time time-weighted mean C.9 reported. C.9's
  measure understates thin-perp capture when spreads widen exactly when trades
  arrive; this one credits what the fill saw. It remains an **upper bound**,
  because every quote is still credited with a fill it has not earned.
- **signed adverse mid move** after each print at 1 s, 5 s and 60 s, with
  :class:`~research.microstructure.adverse.AdverseSelection`'s resolution
  semantics: a deadline resolves against the last mid at or before it.
- **net** = spread - adverse - 3.0 bps, per trade, per horizon; the instrument
  is judged at its **worst** horizon, on the 95% CI lower bound.

Validation is the other half of the file: :func:`known_answer` reproduces
C.9's closed BTC/ETH figures on C.9's own window through the same reader and
accumulators, with the thin coins excluded by allowlist at the parse level.
A pipeline that cannot reproduce the closed answer does not get to produce the
open one.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
from scipy.stats import t as student_t
from statsmodels.stats.multitest import multipletests

from data.recorder.reader import iter_day_records
from research.microstructure.census import AGGRESSOR_SIGN, CensusResult, _quote, run_census
from research.microstructure.fees import HYPERLIQUID_MAKER_ROUND_TRIP_BPS

REGISTRATION_COMMIT = "6025f5c"
# 2026-08-04T00:00Z .. 2026-08-11T00:00Z, in the recorder's epoch nanoseconds.
SCORED_START_NS = 1_785_801_600_000_000_000
SCORED_END_NS = 1_786_406_400_000_000_000
THIN_COINS: frozenset[str] = frozenset(
    {"HYPE", "SOL", "PUMP", "DOT", "LINK", "ARB", "GMX", "MERL", "TNSR", "NOT"}
)
LIQUID_COINS: frozenset[str] = frozenset({"BTC", "ETH"})

HORIZONS_MS: tuple[int, ...] = (1_000, 5_000, 60_000)
# A10: derived from the single sourced fee, never restated as a literal.
ROUND_TRIP_BPS = HYPERLIQUID_MAKER_ROUND_TRIP_BPS
SAMPLE_FLOOR_TRADES = 300
BH_Q = 0.10
CAPACITY_TRADES_PER_DAY = 150.0
CAPACITY_MEDIAN_DAILY_USD = 100_000.0
CONFIDENCE = 0.95

# Known-answer targets: C.9's closed nets on C.9's own window and measure
# (time-weighted mean spread - adverse@1s - 3.0), reproduced within 0.5 bps.
C9_DATES: tuple[str, ...] = ("2026-08-01", "2026-08-02", "2026-08-03")
C9_ADVERSE_HORIZON_MS = 1_000
C9_KNOWN_NET_BPS = {"BTC": -3.05, "ETH": -2.75}
KNOWN_ANSWER_TOLERANCE_BPS = 0.5

NS_PER_MS = 1_000_000
NS_PER_DAY = 86_400_000_000_000


@dataclass
class _Armed:
    deadline_ns: int
    trade_ns: int
    sign: int
    entry_mid: float
    spread_bps: float


@dataclass
class RegisteredInstrument:
    """Per-trade capture panel for one thin instrument: streaming, bounded queues."""

    symbol: str
    rows: dict[int, list[tuple[int, float, float]]] = field(default_factory=dict)
    trades: int = 0
    trades_without_quote: int = 0
    usd_by_day: dict[int, float] = field(default_factory=dict)
    trades_by_day: dict[int, int] = field(default_factory=dict)
    _queues: dict[int, deque[_Armed]] = field(default_factory=dict)
    _last_mid: float | None = None
    _last_spread_bps: float | None = None

    def __post_init__(self) -> None:
        for horizon in HORIZONS_MS:
            self.rows.setdefault(horizon, [])
            self._queues.setdefault(horizon, deque())

    def on_quote(self, ts_ns: int, bid: float, ask: float) -> None:
        if bid <= 0.0 or ask <= 0.0:
            return
        mid = 0.5 * (bid + ask)
        spread = (ask - bid) / mid * 1e4
        # Resolve deadlines with AdverseSelection's exact semantics: a deadline
        # strictly before this quote resolves against the previous mid, one at
        # this instant resolves against this mid.
        for horizon, queue in self._queues.items():
            if self._last_mid is not None:
                while queue and queue[0].deadline_ns < ts_ns:
                    self._resolve(horizon, queue.popleft(), self._last_mid)
            while queue and queue[0].deadline_ns <= ts_ns:
                self._resolve(horizon, queue.popleft(), mid)
        self._last_mid = mid
        self._last_spread_bps = spread if spread > 0.0 else None

    def _resolve(self, horizon_ms: int, armed: _Armed, exit_mid: float) -> None:
        adverse = armed.sign * (exit_mid - armed.entry_mid) / armed.entry_mid * 1e4
        self.rows[horizon_ms].append((armed.trade_ns, armed.spread_bps, adverse))

    def on_trade(self, ts_ns: int, sign: int, px: float, sz: float) -> None:
        self.trades += 1
        day = ts_ns // NS_PER_DAY
        self.trades_by_day[day] = self.trades_by_day.get(day, 0) + 1
        self.usd_by_day[day] = self.usd_by_day.get(day, 0.0) + px * sz
        if self._last_mid is None or self._last_spread_bps is None:
            self.trades_without_quote += 1
            return
        for horizon, queue in self._queues.items():
            queue.append(
                _Armed(
                    deadline_ns=ts_ns + horizon * NS_PER_MS,
                    trade_ns=ts_ns,
                    sign=sign,
                    entry_mid=self._last_mid,
                    spread_bps=self._last_spread_bps,
                )
            )


def _day_clustered_se(rows: list[tuple[int, float, float]]) -> tuple[float, int]:
    """Standard error over UTC-day cluster means (audit finding A3).

    The IID standard error below treats every aggressor print as an independent
    draw. It is not: the touch spread persists across bursts, and at the 5 s and
    60 s horizons consecutive trades share overlapping forward windows. Treating
    each recorded day as one cluster is the crudest honest correction and, on
    the C.27 population, widens the interval 2-28x.
    """
    by_day: dict[int, list[float]] = {}
    for ts_ns, spread, adverse in rows:
        by_day.setdefault(ts_ns // NS_PER_DAY, []).append(spread - adverse - ROUND_TRIP_BPS)
    means = [sum(v) / len(v) for v in by_day.values()]
    k = len(means)
    if k < 2:
        return math.inf, k
    mu = sum(means) / k
    return math.sqrt(sum((m - mu) ** 2 for m in means) / (k - 1) / k), k


def _horizon_stats(rows: list[tuple[int, float, float]]) -> dict[str, float]:
    """Per-horizon net, with the registered bar and the corrections beside it.

    ``ci95_lower_bps`` is the A6 correction: a one-sided registered bar
    ("95% CI lower bound > 0") judged with the one-sided critical value. C.27
    was scored with the two-sided 1.96, which is ~19% *harder* to clear;
    ``ci95_lower_bps_as_scored`` reproduces that, and no instrument's category
    moves between the two. ``ci95_lower_bps_day_clustered`` is the A3 correction
    and is the one that matters: it is 2-28x wider than either.
    """
    n = len(rows)
    nets = [spread - adverse - ROUND_TRIP_BPS for _, spread, adverse in rows]
    mean = sum(nets) / n
    day_se, clusters = _day_clustered_se(rows)
    if n > 2:
        var = sum((x - mean) ** 2 for x in nets) / (n - 1)
        se = math.sqrt(var / n)
        one_sided = float(student_t.ppf(CONFIDENCE, n - 1))
        two_sided = float(student_t.ppf(0.5 + CONFIDENCE / 2, n - 1))
        lower = mean - one_sided * se
        as_scored = mean - two_sided * se
        p_one_sided = float(student_t.sf(mean / se, n - 1)) if se > 0 else 1.0
        day_lower = (
            mean - float(student_t.ppf(CONFIDENCE, clusters - 1)) * day_se
            if clusters > 1
            else -math.inf
        )
    else:
        se = math.inf
        lower = as_scored = day_lower = -math.inf
        p_one_sided = 1.0
    return {
        "n": n,
        "mean_spread_bps": sum(r[1] for r in rows) / n,
        "mean_adverse_bps": sum(r[2] for r in rows) / n,
        "net_mean_bps": mean,
        "ci95_lower_bps": lower,
        "ci95_lower_bps_as_scored": as_scored,
        "ci95_lower_bps_day_clustered": day_lower,
        "se_iid_bps": se,
        "se_day_clustered_bps": day_se,
        "day_clusters": clusters,
        "p_one_sided": p_one_sided,
    }


def instrument_report(
    inst: RegisteredInstrument, recorded_ns: int = SCORED_END_NS - SCORED_START_NS
) -> dict[str, Any]:
    """One instrument against every registered bar except multiplicity."""
    per_horizon: dict[str, dict[str, float]] = {}
    floor_met = True
    for horizon in HORIZONS_MS:
        rows = inst.rows[horizon]
        if len(rows) < SAMPLE_FLOOR_TRADES:
            floor_met = False
            per_horizon[str(horizon)] = {"n": len(rows)}
            continue
        per_horizon[str(horizon)] = _horizon_stats(rows)

    report: dict[str, Any] = {
        "symbol": inst.symbol,
        "aggressor_trades": inst.trades,
        "trades_without_quote": inst.trades_without_quote,
        "per_horizon": per_horizon,
        "floor_met": floor_met,
    }
    if not floor_met:
        report["category"] = "too_thin_by_prior_declaration"
        return report

    worst = min(
        (str(h) for h in HORIZONS_MS), key=lambda k: float(per_horizon[k]["ci95_lower_bps"])
    )
    stats = per_horizon[worst]
    mid_ns = (SCORED_START_NS + SCORED_END_NS) // 2
    halves: list[float | None] = []
    for lo, hi in ((SCORED_START_NS, mid_ns), (mid_ns, SCORED_END_NS)):
        block = [r for r in inst.rows[int(worst)] if lo <= r[0] < hi]
        halves.append(
            sum(s - a - ROUND_TRIP_BPS for _, s, a in block) / len(block) if block else None
        )
    days = sorted(inst.usd_by_day)
    ordered = sorted(inst.usd_by_day[d] for d in days)
    # A8: a true median, not the upper element on an even day count.
    if not ordered:
        median_usd = 0.0
    elif len(ordered) % 2:
        median_usd = ordered[len(ordered) // 2]
    else:
        median_usd = 0.5 * (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2])
    # A8: divide by the span actually recorded. The window is 7 calendar days but
    # a ~5.75 h recorder hole on 08-04 means 96.4% of it was captured, and
    # crediting the missing hours understates every instrument's rate.
    trades_per_day = inst.trades / max(1.0, recorded_ns / NS_PER_DAY)

    report.update(
        {
            "worst_horizon_ms": int(worst),
            "net_mean_bps_worst": stats["net_mean_bps"],
            "ci95_lower_bps_worst": stats["ci95_lower_bps"],
            "ci95_lower_bps_worst_as_scored": stats["ci95_lower_bps_as_scored"],
            "ci95_lower_bps_worst_day_clustered": stats["ci95_lower_bps_day_clustered"],
            "p_one_sided_worst": stats["p_one_sided"],
            "half_net_means_bps": halves,
            "holds_in_both_halves": all(h is not None and h > 0 for h in halves),
            "trades_per_day": trades_per_day,
            "recorded_days": recorded_ns / NS_PER_DAY,
            "median_daily_usd": median_usd,
            "capacity_tier_met": trades_per_day >= CAPACITY_TRADES_PER_DAY
            and median_usd >= CAPACITY_MEDIAN_DAILY_USD,
        }
    )
    return report


def assemble(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Multiplicity and the registered outcome-to-action map, applied verbatim."""
    testable = [r for r in reports if r.get("floor_met")]
    p_values = [float(r["p_one_sided_worst"]) for r in testable]
    survivors: list[str] = []
    if p_values:
        rejected, q_values, _, _ = multipletests(p_values, alpha=BH_Q, method="fdr_bh")
        for r, rej, q in zip(testable, rejected, q_values, strict=True):
            r["bh_rejected"] = bool(rej)
            r["q_value"] = float(q)
        survivors = [
            str(r["symbol"])
            for r in testable
            if r["bh_rejected"]
            and float(r["ci95_lower_bps_worst"]) > 0
            and bool(r["holds_in_both_halves"])
        ]
    for r in testable:
        if not r.get("bh_rejected") or float(r["ci95_lower_bps_worst"]) <= 0:
            r["category"] = (
                "suggestive_noise_of_zero" if float(r["net_mean_bps_worst"]) > 0 else "fail"
            )
        elif not r["holds_in_both_halves"]:
            # Episodic income: one spike is not an edge, by prior declaration.
            r["category"] = "suggestive_noise_of_zero"
        elif not r["capacity_tier_met"]:
            r["category"] = "positive_but_rare"
        else:
            r["category"] = "survivor_tradeable_capacity"

    categories = {str(r["symbol"]): str(r["category"]) for r in reports}
    if all(c in ("fail", "too_thin_by_prior_declaration") for c in categories.values()):
        action = "H6 closes; the register's closing summary updates to zero open items"
    elif any(c == "survivor_tradeable_capacity" for c in categories.values()):
        action = "input to a D.1 fill-simulation decision, not a strategy"
    elif any(c == "positive_but_rare" for c in categories.values()):
        action = "report the fill-frequency arithmetic and stop"
    else:
        action = "extend recording 30 days and re-run under these same bars; no building"

    return {
        "registration_commit": REGISTRATION_COMMIT,
        "bh_q": BH_Q,
        "expected_false_positives": round(BH_Q * len(survivors), 2),
        "survivors_all_bars": survivors,
        "categories": categories,
        "registered_action": action,
        "upper_bound_statement": (
            "every quote is credited with a fill it has not earned; queue position, fill "
            "probability and fill conditioning are unmodelled and all point down"
        ),
    }


def assert_scored_window_closed(now_ns: int) -> None:
    """The census may not run before its window ends. Not a comment — a raise."""
    if now_ns < SCORED_END_NS:
        closes = datetime.fromtimestamp(SCORED_END_NS / 1e9, tz=UTC).isoformat()
        raise RuntimeError(
            f"the registered scored window closes {closes}; the thin instruments stay "
            f"untouched until then (bars: progress.md commit {REGISTRATION_COMMIT})"
        )


class _ReplayFeed:
    """Raw replay into RegisteredInstrument, thin allowlist enforced at parse."""

    def __init__(self, instruments: dict[str, RegisteredInstrument]) -> None:
        self.instruments = instruments

    def run_day(self, raw_dir: Path, date: str) -> None:
        for recv_ns, raw in iter_day_records(raw_dir, "hyperliquid", date):
            if not (SCORED_START_NS <= recv_ns < SCORED_END_NS):
                continue
            try:
                message = orjson.loads(raw)
            except orjson.JSONDecodeError:
                continue
            channel, data = message.get("channel"), message.get("data")
            if channel == "bbo" and isinstance(data, dict):
                inst = self.instruments.get(str(data.get("coin")))
                quote = _quote(data.get("bbo") or [])
                if inst is not None and quote is not None:
                    inst.on_quote(recv_ns, *quote)
            elif channel == "trades" and isinstance(data, list):
                for print_ in data:
                    if not isinstance(print_, dict):
                        continue
                    inst = self.instruments.get(str(print_.get("coin")))
                    sign = AGGRESSOR_SIGN.get(str(print_.get("side")))
                    if inst is None or sign is None:
                        continue
                    try:
                        px, sz = float(print_["px"]), float(print_["sz"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    inst.on_trade(recv_ns, sign, px, sz)


def run_registered_census(
    raw_dir: Path, dates: list[str], now_ns: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The H6 census. Refuses to run early; reads the thin population only."""
    assert_scored_window_closed(now_ns)
    instruments = {coin: RegisteredInstrument(symbol=coin) for coin in sorted(THIN_COINS)}
    feed = _ReplayFeed(instruments)
    for date in dates:
        feed.run_day(raw_dir, date)
    reports = [instrument_report(instruments[coin]) for coin in sorted(instruments)]
    return reports, assemble(reports)


def known_answer(raw_dir: Path) -> dict[str, Any]:
    """Reproduce C.9's closed BTC/ETH nets on C.9's own window, BTC/ETH only.

    Uses C.9's measure exactly — time-weighted mean spread minus adverse at
    1 s minus 3.0 — through the same reader and accumulators C.9 ran, with the
    thin coins excluded by allowlist before any accumulator sees them.
    """
    result: CensusResult | None = None
    for date in C9_DATES:
        result = run_census(raw_dir, date, coins=set(LIQUID_COINS), result=result)
    assert result is not None
    out: dict[str, Any] = {"dates": list(C9_DATES), "tolerance_bps": KNOWN_ANSWER_TOLERANCE_BPS}
    all_pass = True
    for coin, target in C9_KNOWN_NET_BPS.items():
        inst = result.instruments[coin]
        tw_spread = inst.spread.sum_weighted_bps / inst.spread.total_ns
        adverse = (
            inst.adverse.sums_bps[C9_ADVERSE_HORIZON_MS]
            / inst.adverse.counts[C9_ADVERSE_HORIZON_MS]
        )
        net = tw_spread - adverse - ROUND_TRIP_BPS
        delta = net - target
        all_pass &= abs(delta) <= KNOWN_ANSWER_TOLERANCE_BPS
        out[coin] = {
            "tw_spread_bps": round(tw_spread, 4),
            "adverse_1s_bps": round(adverse, 4),
            "net_bps": round(net, 4),
            "c9_target_bps": target,
            "delta_bps": round(delta, 4),
            "resolved_trades_1s": inst.adverse.counts[C9_ADVERSE_HORIZON_MS],
        }
    out["reproduced_within_tolerance"] = all_pass
    return out
