"""Tests for trading healthcheck helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.scheduler.trading_healthcheck import _latest_cycle_timestamp


def test_latest_cycle_timestamp_returns_none_when_file_missing(tmp_path: Path) -> None:
    """Missing cycle log should return no timestamp."""
    assert _latest_cycle_timestamp(tmp_path / "missing.jsonl") is None


def test_latest_cycle_timestamp_reads_last_record(tmp_path: Path) -> None:
    """Cycle healthcheck should read the newest recorded_at value."""
    log_path = tmp_path / "cycle.jsonl"
    records = [
        {"cycle": 1, "recorded_at": "2026-03-24T19:02:00+00:00"},
        {"cycle": 2, "recorded_at": "2026-03-24T19:32:00+00:00"},
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    assert _latest_cycle_timestamp(log_path) == "2026-03-24T19:32:00+00:00"
