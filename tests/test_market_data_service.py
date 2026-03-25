"""Tests for trading market-data readiness checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from app.data.data_normalizer import MarketDataService
from app.utils.models import Candle


def _build_config() -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(min_candles_required=3, max_data_staleness_minutes=90),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env={},
        cache_path="",
    )


def test_validate_candles_rejects_short_history() -> None:
    """Trading should fail closed when candle history is too short."""
    service = MarketDataService(_build_config())
    candles = [
        Candle(timestamp=datetime.now(UTC), open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=datetime.now(UTC), open=1, high=1, low=1, close=1, volume=1),
    ]
    ok, reason = service.validate_candles(candles)
    assert ok is False
    assert reason.startswith("insufficient_history")


def test_validate_candles_rejects_stale_data() -> None:
    """Trading should fail closed when the latest candle is stale."""
    service = MarketDataService(_build_config())
    stale_time = datetime.now(UTC) - timedelta(minutes=120)
    candles = [
        Candle(timestamp=stale_time, open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=stale_time, open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=stale_time, open=1, high=1, low=1, close=1, volume=1),
    ]
    ok, reason = service.validate_candles(candles)
    assert ok is False
    assert reason.startswith("stale_data")
