from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
from app.config.settings import load_config
from app.data.data_normalizer import MarketDataService
from app.scheduler import collector_runner, worker_runner
from app.utils.models import Candle


def _config(*, demo_mode: bool = False) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env={},
        cache_path="",
        demo_mode=demo_mode,
    )


def test_load_config_reads_demo_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    config = load_config()
    assert config.demo_mode is True


def test_market_data_service_allows_stale_data_in_demo_mode() -> None:
    config = _config(demo_mode=True)
    service = MarketDataService(config=config)
    stale_timestamp = datetime.now(UTC) - timedelta(days=30)
    candles = [
        Candle(
            timestamp=stale_timestamp + timedelta(minutes=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        for index in range(config.data.min_candles_required)
    ]
    is_ready, reason = service.validate_candles(candles)

    assert is_ready is True
    assert reason.startswith("demo_mode_skip_staleness:")


def test_collector_runner_exits_cleanly_in_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector_runner, "load_config", lambda: _config(demo_mode=True))
    monkeypatch.setattr(collector_runner, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        collector_runner,
        "CoinbaseIngestionService",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Coinbase should not initialize in demo mode")),
    )

    collector_runner.run()


def test_worker_runner_skips_coinbase_initialization_in_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    class StopLoop(Exception):
        pass

    monkeypatch.setattr(worker_runner, "load_config", lambda: _config(demo_mode=True))
    monkeypatch.setattr(worker_runner, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker_runner,
        "CoinbaseIngestionService",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Coinbase should not initialize in demo mode")),
    )
    monkeypatch.setattr(worker_runner, "sleep_until_datetime", lambda *args, **kwargs: (_ for _ in ()).throw(StopLoop()))

    with pytest.raises(StopLoop):
        worker_runner.run()
