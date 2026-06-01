"""Tests for combined worker boundary alignment helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config.schema import (
    AppConfig,
    DataConfig,
    ExecutionConfig,
    IngestionConfig,
    LLMConfig,
    LoggingConfig,
    NotificationConfig,
    RuntimeConfig,
    TradingConfig,
)
from app.monitoring.weekly_report import should_send_weekly_report
from app.scheduler.worker_runner import _next_boundary


def _config() -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env={"REPORT_TIMEZONE": "America/Toronto"},
        cache_path="",
    )


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


def test_should_send_weekly_report_only_in_monday_nine_am_window() -> None:
    """Weekly report scheduling should trigger once during the Monday 9 AM local hour."""
    config = _config()
    monday_nine = datetime(2026, 6, 1, 13, 5, tzinfo=UTC)
    should_send, report_key = should_send_weekly_report(now=monday_nine, config=config, last_sent_key=None)
    should_not_send, _ = should_send_weekly_report(now=monday_nine, config=config, last_sent_key=report_key)
    tuesday_nine = datetime(2026, 6, 2, 13, 5, tzinfo=UTC)
    wrong_day, _ = should_send_weekly_report(now=tuesday_nine, config=config, last_sent_key=None)

    assert should_send is True
    assert should_not_send is False
    assert wrong_day is False
