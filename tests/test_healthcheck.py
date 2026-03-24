"""Tests for ingestion healthcheck logic."""

from __future__ import annotations

from datetime import UTC, datetime

from app.scheduler.healthcheck import is_state_fresh


def test_is_state_fresh_returns_true_for_recent_heartbeat() -> None:
    """Recent heartbeats should pass the healthcheck."""
    now = datetime(2026, 3, 24, 19, 0, tzinfo=UTC)
    heartbeat = datetime(2026, 3, 24, 18, 30, tzinfo=UTC).isoformat()
    assert is_state_fresh(heartbeat, max_staleness_minutes=45, now=now) is True


def test_is_state_fresh_returns_false_for_stale_heartbeat() -> None:
    """Stale heartbeats should fail the healthcheck."""
    now = datetime(2026, 3, 24, 19, 0, tzinfo=UTC)
    heartbeat = datetime(2026, 3, 24, 17, 30, tzinfo=UTC).isoformat()
    assert is_state_fresh(heartbeat, max_staleness_minutes=45, now=now) is False
