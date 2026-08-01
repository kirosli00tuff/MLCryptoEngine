"""Append-only experiment log: every training run, from the first one.

A deflated Sharpe ratio — or any honest multiple-testing correction — is only
computable if the number and shape of trials is known, and that only works if
the log exists from the first experiment rather than being retrofitted after
the survivors are chosen. Every entry records configuration, data range,
feature set, label definition, cost assumption, and results, plus the git
commit so the code that produced a number can be recovered.

The log lives at ``research/experiments.jsonl`` and is committed to the repo
(it is a versioned research record, not a build artifact).
"""

from __future__ import annotations

import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from data.config import REPO_ROOT

EXPERIMENTS_PATH = REPO_ROOT / "research" / "experiments.jsonl"


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def log_experiment(entry: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Append one run record; returns the full entry (with run_id/stamp/sha).

    Caller-supplied keys are preserved verbatim; ``run_id``, ``logged_at``,
    and ``git_sha`` are added here so no run can forget them.
    """
    target = path if path is not None else EXPERIMENTS_PATH
    record = {
        "run_id": str(uuid.uuid4()),
        "logged_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        **entry,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("ab") as fh:
        fh.write(orjson.dumps(record) + b"\n")
    return record


def read_experiments(path: Path | None = None) -> list[dict[str, Any]]:
    target = path if path is not None else EXPERIMENTS_PATH
    if not target.is_file():
        return []
    entries: list[dict[str, Any]] = []
    with target.open("rb") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                entries.append(orjson.loads(stripped))
    return entries
