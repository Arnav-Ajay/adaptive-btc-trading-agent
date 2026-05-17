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
from app.strategies.pullback_selector import PullbackHybridSelector
from app.utils.models import AgentContext, MarketRegime, PortfolioSnapshot, Signal, StrategyOutcome, SwingPosition, TradeSide


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


def test_selector_suppresses_dca_when_pullback_entry_exists() -> None:
    config = _build_config()
    selector = PullbackHybridSelector(config=config)
    context = AgentContext(config=config)
    context.market_regime = MarketRegime.BULLISH
    pullback_outcome = StrategyOutcome(
        strategy_name="PullbackTrendStrategy",
        signals=[
            Signal(
                side=TradeSide.BUY,
                symbol="BTC-USD",
                size_usd=250.0,
                reason="pullback_trend_entry",
                strategy_name="PullbackTrendStrategy",
            )
        ],
        trace=["decision:bullish_pullback_entry"],
    )

    selection = selector.select(context=context, pullback_outcome=pullback_outcome)

    assert selection.allow_dca is False
    assert selection.allow_pullback is True
    assert selection.mode == "pullback_priority_signal"


def test_selector_suppresses_dca_with_open_pullback_position() -> None:
    config = _build_config()
    selector = PullbackHybridSelector(config=config)
    context = AgentContext(config=config)
    context.market_regime = MarketRegime.BULLISH
    context.active_swing_positions = [
        SwingPosition(
            position_id="p1",
            symbol="BTC-USD",
            entry_price=100.0,
            stop_loss=95.0,
            btc_units=1.0,
            size_usd=100.0,
            opened_at="2026-01-01T00:00:00+00:00",
            strategy_name="PullbackTrendStrategy",
        )
    ]
    pullback_outcome = StrategyOutcome(strategy_name="PullbackTrendStrategy", signals=[], trace=["hold:pullback_position"])

    selection = selector.select(context=context, pullback_outcome=pullback_outcome)

    assert selection.allow_dca is False
    assert selection.mode == "pullback_priority_open_position"


def test_selector_blocks_dca_in_bearish_when_config_disables_it() -> None:
    config = _build_config()
    config.trading.hybrid_dca_enabled_in_bearish = False
    selector = PullbackHybridSelector(config=config)
    context = AgentContext(config=config)
    context.market_regime = MarketRegime.BEARISH
    pullback_outcome = StrategyOutcome(strategy_name="PullbackTrendStrategy", signals=[], trace=["skip:pullback_regime_blocked"])

    selection = selector.select(context=context, pullback_outcome=pullback_outcome)

    assert selection.allow_dca is False
    assert selection.mode == "pullback_only_risk_filter"


def test_selector_allows_parallel_when_no_pullback_priority_condition_exists() -> None:
    config = _build_config()
    selector = PullbackHybridSelector(config=config)
    context = AgentContext(config=config)
    context.market_regime = MarketRegime.BULLISH
    context.portfolio_snapshot = PortfolioSnapshot(
        cash_usd=9_500.0,
        btc_units=0.005,
        equity_usd=10_000.0,
        drawdown_percent=0.0,
        last_mark_price=60_000.0,
    )
    pullback_outcome = StrategyOutcome(strategy_name="PullbackTrendStrategy", signals=[], trace=["skip:pullback_regime_blocked"])

    selection = selector.select(context=context, pullback_outcome=pullback_outcome)

    assert selection.allow_dca is True
    assert selection.allow_pullback is True
    assert selection.mode == "hybrid_parallel"


def test_selector_blocks_dca_in_sideways_by_default() -> None:
    config = _build_config()
    selector = PullbackHybridSelector(config=config)
    context = AgentContext(config=config)
    context.market_regime = MarketRegime.SIDEWAYS
    pullback_outcome = StrategyOutcome(strategy_name="PullbackTrendStrategy", signals=[], trace=["skip:pullback_regime_blocked"])

    selection = selector.select(context=context, pullback_outcome=pullback_outcome)

    assert selection.allow_dca is False
    assert selection.mode == "pullback_only_risk_filter"


def test_selector_blocks_bullish_dca_when_allocation_cap_is_reached() -> None:
    config = _build_config()
    config.trading.hybrid_bullish_dca_max_allocation_percent = 20.0
    selector = PullbackHybridSelector(config=config)
    context = AgentContext(config=config)
    context.market_regime = MarketRegime.BULLISH
    context.portfolio_snapshot = PortfolioSnapshot(
        cash_usd=7_500.0,
        btc_units=0.05,
        equity_usd=10_000.0,
        drawdown_percent=0.0,
        last_mark_price=60_000.0,
    )
    pullback_outcome = StrategyOutcome(strategy_name="PullbackTrendStrategy", signals=[], trace=["skip:no_price_stabilization"])

    selection = selector.select(context=context, pullback_outcome=pullback_outcome)

    assert selection.allow_dca is False
    assert selection.mode == "pullback_only_risk_filter"
