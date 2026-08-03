"""Vendor downloads stream to disk and never leave a truncated file behind.

Stage C.7 committed $35.51 for June MBP-10, then lost the process to the OOM
killer mid-fetch because the client had been asked to build the whole month in
memory before writing any of it. These tests pin both halves of the fix: the
request streams to a path, and an interrupted stream cannot be mistaken for a
finished download by the next run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from data.databento.ingest import _download_to_file

PAYLOAD = b"\x01DBN-body-bytes"


class _FakeTimeseries:
    """Stands in for ``client.timeseries``, writing to whatever path it is given."""

    def __init__(self, payload: bytes, *, fail: bool = False) -> None:
        self._payload = payload
        self._fail = fail
        self.calls: list[dict[str, Any]] = []

    def get_range(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        path = kwargs.get("path")
        if path is None:
            raise AssertionError("response was buffered in memory instead of streamed")
        Path(path).write_bytes(self._payload)
        if self._fail:
            raise RuntimeError("connection reset mid-stream")


class _FakeClient:
    def __init__(self, timeseries: _FakeTimeseries) -> None:
        self.timeseries = timeseries


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "range=2026-06-01_2026-07-01" / "MBT_c_0.mbp-10.dbn.zst"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _download(client: _FakeClient, target: Path) -> None:
    _download_to_file(
        client,
        target,
        symbol="MBT.c.0",
        schema="mbp-10",
        start="2026-06-01",
        end="2026-07-01",
    )


def test_download_streams_to_a_path_then_renames_into_place(tmp_path: Path) -> None:
    # Arrange
    timeseries = _FakeTimeseries(PAYLOAD)
    target = _target(tmp_path)

    # Act
    _download(_FakeClient(timeseries), target)

    # Assert
    assert target.read_bytes() == PAYLOAD
    assert list(target.parent.iterdir()) == [target], "no .partial residue after success"
    (call,) = timeseries.calls
    assert call["path"] == target.parent / (target.name + ".partial"), (
        "the month must stream to a temp path, never be materialised in memory"
    )
    assert (call["start"], call["end"]) == ("2026-06-01", "2026-07-01")


def test_interrupted_download_leaves_nothing_at_the_target_path(tmp_path: Path) -> None:
    # Arrange
    timeseries = _FakeTimeseries(b"only-the-first-week", fail=True)
    target = _target(tmp_path)

    # Act
    with pytest.raises(RuntimeError):
        _download(_FakeClient(timeseries), target)

    # Assert
    assert not target.exists(), "a truncated month must never occupy the real path"
    assert list(target.parent.iterdir()) == [], "and must not leave a .partial corpse"


def test_retry_discards_a_partial_left_by_a_killed_run(tmp_path: Path) -> None:
    # Arrange: the OOM killer leaves no chance to clean up, so the next run
    # finds a half-written .partial from the previous attempt.
    target = _target(tmp_path)
    stale = target.parent / (target.name + ".partial")
    stale.write_bytes(b"bytes from the run the OOM killer took")
    timeseries = _FakeTimeseries(PAYLOAD)

    # Act
    _download(_FakeClient(timeseries), target)

    # Assert
    assert target.read_bytes() == PAYLOAD, "the retry must replace the corpse, not append"
