# app/scheduler/job_runner.py
"""Scheduling helpers for long-running execution."""

from __future__ import annotations

from datetime import datetime, timedelta
import time


def sleep_until_next_cycle(interval_seconds: int) -> None:
    """Sleep until the next cycle boundary."""
    time.sleep(max(interval_seconds, 0))


def seconds_until_next_interval(interval_minutes: int, now: datetime | None = None) -> float:
    """Return seconds until the next aligned interval boundary."""
    if interval_minutes <= 0:
        return 0.0

    current = now or datetime.now().astimezone()
    aligned_minute = (current.minute // interval_minutes) * interval_minutes
    boundary = current.replace(minute=aligned_minute, second=0, microsecond=0)
    if boundary <= current:
        boundary += timedelta(minutes=interval_minutes)
    return max((boundary - current).total_seconds(), 0.0)
