"""Phase B report sections: results with the caveat welded on.

Every section leads with how little data the numbers rest on. A promising
metric computed on a handful of days from one volatility regime is pipeline
validation, not a discovery, and the report format makes that impossible to
miss or quietly drop.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_phase_b_section(payload: dict[str, Any]) -> str:
    """Markdown for one Phase B run. ``payload`` is the pipeline's result dict."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    dates: list[str] = payload["dates"]
    regimes: int = payload.get("volatility_regimes", 1)
    lines = [f"\n## Phase B research run — {stamp}\n"]
    lines.append(
        f"**Caveat, read first: these results rest on {len(dates)} day(s) of data "
        f"spanning ~{regimes} volatility regime(s). They validate the pipeline; "
        "they are NOT evidence of edge. Microstructure relationships shift with "
        "regime, session, and venue conditions — a signal fitted on one day is "
        "fitted on that day's regime.**\n"
    )
    lines.append(
        f"Data range: {', '.join(dates)} · sampling: {payload['sampling']} · "
        f"features: {payload['feature_count']} · labels: fixed-horizon "
        f"{payload['horizons_ms']} ms + triple-barrier ({payload['tb_config']}) · "
        f"cost assumptions: {payload['cost_summary']} · trade signing: "
        f"{payload['signing_methods']}"
    )
    lines.append("")
    leakage = payload.get("leakage_tests", "not run in this invocation")
    lines.append(f"Leakage suite: {leakage}")
    lines.append("")
    for key, block in payload["results"].items():
        lines.append(f"### {key}")
        lines.append("")
        if "error" in block:
            lines.append(f"- ✗ {block['error']}")
            lines.append("")
            continue
        lines.append(f"Valid samples: {block['n_samples']:,}")
        lines.append("")
        lines.append(
            "| horizon | n | AUC | cost mode | model EV bps | model hit | "
            "regressor EV bps | last-sign EV bps | zero EV bps |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for horizon_ms, hres in block["horizons"].items():
            if "skipped" in hres:
                lines.append(f"| {horizon_ms} ms | — | — | — | {hres['skipped']} | | | | |")
                continue
            for mode, entries in hres["cost_modes"].items():
                clf = entries["model_classifier"]
                reg = entries["model_regressor"]
                last = entries["baseline_last_sign"]
                zero = entries["baseline_zero"]
                lines.append(
                    f"| {horizon_ms} ms | {hres['n']} | {_fmt(hres['auc'])} | {mode} "
                    f"| {_fmt(clf['ev_bps_net'], 2)} | {_fmt(clf['hit_rate'])} "
                    f"| {_fmt(reg['ev_bps_net'], 2)} | {_fmt(last['ev_bps_net'], 2)} "
                    f"| {_fmt(zero['ev_bps_net'], 2)} |"
                )
        lines.append("")
        decay = [
            f"{h} ms: {_fmt(hres.get('auc'))}"
            for h, hres in block["horizons"].items()
            if "skipped" not in hres
        ]
        lines.append(f"Predictability decay (AUC by horizon): {' · '.join(decay) or 'n/a'}")
        importances: dict[str, float] = next(
            (
                hres["feature_importances_top10"]
                for hres in block["horizons"].values()
                if "feature_importances_top10" in hres
            ),
            {},
        )
        if importances:
            top = " · ".join(f"{name} {share:.2f}" for name, share in importances.items())
            lines.append(f"\nTop feature importances (fold-averaged): {top}")
        lines.append("")
    return "\n".join(lines)


def append_phase_b_section(report_path: Path, payload: dict[str, Any]) -> None:
    with report_path.open("a", encoding="utf-8") as fh:
        fh.write(render_phase_b_section(payload))
