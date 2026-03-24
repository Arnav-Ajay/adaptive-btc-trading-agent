"""Scheduling helpers for long-running execution."""

from __future__ import annotations

import time


def sleep_until_next_cycle(interval_seconds: int) -> None:
    """Sleep until the next cycle boundary."""
    time.sleep(max(interval_seconds, 0))

