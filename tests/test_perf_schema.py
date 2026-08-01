"""PerformanceReport contract: mode is mandatory, generated types cannot drift."""

from __future__ import annotations

import pydantic
import pytest

from backtest.reporting.schema import (
    CostAssumption,
    LatencyPercentiles,
    Mode,
    PerformanceReport,
    SlippageStats,
)
from backtest.reporting.ts_export import (
    JSON_SCHEMA_PATH,
    TS_PATH,
    render_json_schema,
    render_typescript,
)


def _report_kwargs() -> dict[str, object]:
    return {
        "run_id": "run-1",
        "venue": "kraken",
        "symbol": "BTC/USD",
        "data_start_ns": 1,
        "data_end_ns": 2,
        "cost": CostAssumption(mode="maker", fee_bps_per_leg=1.6, includes_spread=False),
        "equity_curve": [],
        "drawdown": [],
        "trades": [],
        "expectancy_bps_net": 0.0,
        "slippage": SlippageStats(expected_bps=0.0, realized_bps=0.0),
        "latency": LatencyPercentiles(p50_ms=10.0, p95_ms=20.0, p99_ms=30.0),
    }


def test_mode_is_required_and_has_no_default() -> None:
    with pytest.raises(pydantic.ValidationError, match="mode"):
        PerformanceReport(**_report_kwargs())  # type: ignore[arg-type]
    assert PerformanceReport.model_fields["mode"].is_required(), (
        "a report that cannot state simulation vs real money is not a valid report"
    )
    report = PerformanceReport(mode=Mode.BACKTEST, **_report_kwargs())  # type: ignore[arg-type]
    assert report.mode is Mode.BACKTEST


def test_committed_generated_types_match_current_schema() -> None:
    """Drift between schema.py and the committed generated files fails here,
    not in the desktop UI. Regenerate with `make types`."""
    assert TS_PATH.is_file(), "generated TS types missing — run `make types` and commit"
    assert JSON_SCHEMA_PATH.is_file(), "JSON schema missing — run `make types` and commit"
    assert TS_PATH.read_text(encoding="utf-8") == render_typescript()
    assert JSON_SCHEMA_PATH.read_text(encoding="utf-8") == render_json_schema()


def test_generated_typescript_is_marked_generated_and_types_mode_strictly() -> None:
    rendered = render_typescript()
    assert rendered.startswith("// GENERATED FILE — do not edit by hand.")
    assert 'export type Mode = "backtest" | "paper" | "live";' in rendered
    assert "mode: Mode;" in rendered
