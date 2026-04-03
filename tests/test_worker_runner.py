"""Tests for combined worker boundary alignment helpers."""

from __future__ import annotations

from datetime import datetime

from app.scheduler.worker_runner import _next_boundary


def test_next_boundary_aligns_to_next_window() -> None:
    """Worker boundary helper should align to the next interval boundary."""
    now = datetime.fromisoformat("2026-03-29T07:01:08+00:00")
    boundary = _next_boundary(30, now=now)
    assert boundary.isoformat() == "2026-03-29T07:30:00+00:00"


def test_next_boundary_rolls_forward_from_exact_boundary() -> None:
    """Worker boundary helper should roll to the next interval when already on a boundary."""
    now = datetime.fromisoformat("2026-03-29T07:00:00+00:00")
    boundary = _next_boundary(30, now=now)
    assert boundary.isoformat() == "2026-03-29T07:30:00+00:00"
