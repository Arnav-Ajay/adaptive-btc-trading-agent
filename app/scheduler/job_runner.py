# app/scheduler/job_runner.py
"""Scheduling helpers for long-running execution."""

from __future__ import annotations

from datetime import datetime, timedelta
import time
from typing import Callable


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


def sleep_until_datetime(
    target: datetime,
    *,
    now_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Sleep until a target datetime using shorter final waits for better boundary accuracy."""
    current_time = now_provider or (lambda: datetime.now(target.tzinfo))
    while True:
        remaining = (target - current_time()).total_seconds()
        if remaining <= 0:
            return
        if remaining > 60:
            sleeper(min(remaining, 60.0))
            continue
        if remaining > 1:
            sleeper(min(remaining, 1.0))
            continue
        sleeper(remaining)
