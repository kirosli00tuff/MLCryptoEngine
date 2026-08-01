"""Generate JSON Schema and TypeScript types from the PerformanceReport models.

Deterministic output, committed to the repo, regenerated with ``make types``.
Generated files are never edited by hand — a test regenerates and compares,
so drift between the Python contract and the desktop types fails CI instead
of surfacing as a broken panel.
"""

from __future__ import annotations

import json
import types
import typing
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel

from backtest.reporting.schema import (
    CostAssumption,
    DrawdownPoint,
    EquityPoint,
    LatencyPercentiles,
    Mode,
    PerformanceReport,
    SlippageStats,
    TradeRecord,
)
from data.config import REPO_ROOT

GENERATED_DIR = REPO_ROOT / "desktop" / "src" / "lib" / "generated"
TS_PATH = GENERATED_DIR / "performance-report.ts"
JSON_SCHEMA_PATH = REPO_ROOT / "backtest" / "reporting" / "performance_report.schema.json"

# Export order is fixed so output is byte-stable across runs.
MODELS: list[type[BaseModel]] = [
    CostAssumption,
    EquityPoint,
    DrawdownPoint,
    TradeRecord,
    SlippageStats,
    LatencyPercentiles,
    PerformanceReport,
]

HEADER = """\
// GENERATED FILE — do not edit by hand.
// Source of truth: backtest/reporting/schema.py · regenerate with `make types`.

"""


def _ts_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        parts = [_ts_type(arg) for arg in get_args(annotation)]
        return " | ".join(dict.fromkeys(parts))
    if origin is list:
        return f"{_ts_type(get_args(annotation)[0])}[]"
    if origin is Literal:
        return " | ".join(json.dumps(arg) for arg in get_args(annotation))
    if annotation is type(None):
        return "null"
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return annotation.__name__
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__
    if annotation is str:
        return "string"
    if annotation in (int, float):
        return "number"
    if annotation is bool:
        return "boolean"
    raise TypeError(f"No TypeScript mapping for {annotation!r}")


def render_typescript() -> str:
    parts = [HEADER]
    mode_values = " | ".join(json.dumps(m.value) for m in Mode)
    parts.append(f"export type {Mode.__name__} = {mode_values};\n\n")
    for model in MODELS:
        parts.append(f"export interface {model.__name__} {{\n")
        for name, field in model.model_fields.items():
            parts.append(f"  {name}: {_ts_type(field.annotation)};\n")
        parts.append("}\n\n")
    return "".join(parts).rstrip() + "\n"


def render_json_schema() -> str:
    schema = PerformanceReport.model_json_schema()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_generated(
    ts_path: Path = TS_PATH, json_schema_path: Path = JSON_SCHEMA_PATH
) -> tuple[Path, Path]:
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    json_schema_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.write_text(render_typescript(), encoding="utf-8")
    json_schema_path.write_text(render_json_schema(), encoding="utf-8")
    return ts_path, json_schema_path
