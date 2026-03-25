"""Tests for strategy routing behavior."""

from __future__ import annotations

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
from app.strategies.hybrid import HybridStrategy
from app.strategies.dca import DCAStrategy
from app.strategies.router import StrategyRouter
from app.utils.models import MarketRegime


def _build_config() -> AppConfig:
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
    )


def test_router_uses_hybrid_strategy_in_bullish_regime() -> None:
    """Bullish regimes should keep DCA active while allowing swing entries."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(MarketRegime.BULLISH)
    assert isinstance(strategy, HybridStrategy)


def test_router_uses_dca_strategy_outside_bullish_regime() -> None:
    """Non-bullish regimes should use the base DCA strategy."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(MarketRegime.BEARISH)
    assert isinstance(strategy, DCAStrategy)
