"""Tests for scheduler interval alignment helpers."""

from __future__ import annotations

from datetime import datetime

from app.scheduler.job_runner import seconds_until_next_interval_with_offset


def test_seconds_until_next_interval_with_offset_aligns_to_next_window() -> None:
    """Offset interval helper should align to the next scheduled decision window."""
    now = datetime.fromisoformat("2026-03-24T12:01:00+00:00")
    seconds = seconds_until_next_interval_with_offset(30, 2, now=now)
    assert seconds == 60.0


def test_seconds_until_next_interval_with_offset_rolls_forward_after_offset() -> None:
    """Offset interval helper should roll to the next interval after the offset is passed."""
    now = datetime.fromisoformat("2026-03-24T12:03:00+00:00")
    seconds = seconds_until_next_interval_with_offset(30, 2, now=now)
    assert seconds == 29 * 60.0
