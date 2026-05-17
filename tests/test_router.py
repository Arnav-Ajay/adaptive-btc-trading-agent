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


def test_router_uses_dca_strategy_in_weakening_bull_regime() -> None:
    """Weakening bull should still route to the base DCA layer for regime-aware base-position control."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(MarketRegime.WEAKENING_BULL)
    assert isinstance(strategy, DCAStrategy)


def test_router_keeps_hybrid_strategy_active_when_swing_positions_exist() -> None:
    """Open swing positions should keep the swing exit path available in non-bullish regimes."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(MarketRegime.BEARISH, has_open_swing_positions=True)
    assert isinstance(strategy, HybridStrategy)


def test_router_uses_hybrid_strategy_for_bullish_trend_even_if_regime_is_not_bullish() -> None:
    """A bullish EMA trend should keep the hybrid swing layer available."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(MarketRegime.SIDEWAYS, bullish_trend=True)
    assert isinstance(strategy, HybridStrategy)


def test_router_uses_score_bias_for_hybrid_when_regime_score_is_positive() -> None:
    """A positive scored regime should bias toward the hybrid stack even if the label is not bullish."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(
        MarketRegime.TRANSITION,
        regime_score=0.28,
        regime_confidence=0.55,
        deterioration_score=0.15,
    )
    assert isinstance(strategy, HybridStrategy)


def test_router_uses_dca_when_scored_regime_is_negative() -> None:
    """A negative scored regime should bias toward the base DCA layer."""
    router = StrategyRouter(config=_build_config())
    strategy = router.select(
        MarketRegime.SIDEWAYS,
        regime_score=-0.52,
        regime_confidence=0.72,
        deterioration_score=0.3,
    )
    assert isinstance(strategy, DCAStrategy)
