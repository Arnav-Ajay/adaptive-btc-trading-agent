"""Tests for scheduler interval alignment helpers."""

from __future__ import annotations

from datetime import datetime

from app.scheduler.job_runner import seconds_until_next_interval, sleep_until_datetime


def test_seconds_until_next_interval_aligns_to_next_window() -> None:
    """Interval helper should align to the next scheduled boundary."""
    now = datetime.fromisoformat("2026-03-24T12:01:00+00:00")
    seconds = seconds_until_next_interval(30, now=now)
    assert seconds == 29 * 60.0


def test_seconds_until_next_interval_rolls_forward_after_boundary() -> None:
    """Interval helper should roll forward after a boundary is passed exactly."""
    now = datetime.fromisoformat("2026-03-24T12:30:00+00:00")
    seconds = seconds_until_next_interval(30, now=now)
    assert seconds == 30 * 60.0


def test_sleep_until_datetime_uses_short_final_waits() -> None:
    """Boundary sleep helper should avoid one giant sleep and finish exactly at the target."""
    current = datetime.fromisoformat("2026-03-24T12:00:00+00:00")
    target = datetime.fromisoformat("2026-03-24T12:01:02.500000+00:00")
    sleeps: list[float] = []

    def now_provider() -> datetime:
        return current

    def sleeper(seconds: float) -> None:
        nonlocal current
        sleeps.append(seconds)
        current = current.fromtimestamp(current.timestamp() + seconds, tz=current.tzinfo)

    sleep_until_datetime(target, now_provider=now_provider, sleeper=sleeper)

    assert sleeps == [60.0, 1.0, 1.0, 0.5]
    assert current == target
