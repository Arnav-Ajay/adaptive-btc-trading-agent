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
from app.strategies.swing_atr import SwingATRStrategy
from app.utils.models import AgentContext, Candle, FeatureSet, SwingPosition, TradeSide


def _build_config() -> AppConfig:
    return AppConfig(
        trading=TradingConfig(
            swing_entry_rsi_max=35.0,
            swing_take_profit_percent=2.0,
            swing_no_follow_through_candles=3,
            swing_follow_through_buffer_percent=0.2,
        ),
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


def _candles(count: int = 5) -> list[Candle]:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return [
        Candle(
            timestamp=start + timedelta(minutes=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        for index in range(count)
    ]


def test_swing_strategy_requires_stronger_rsi_reset_for_entry() -> None:
    config = _build_config()
    strategy = SwingATRStrategy(config=config)
    context = AgentContext(config=config)
    context.available_cash_usd = 1_000.0
    features = FeatureSet(
        last_price=100.0,
        atr=2.0,
        rsi=34.0,
        ema_fast=105.0,
        ema_slow=100.0,
        macd_histogram=1.0,
    )

    outcome = strategy.generate(context=context, candles=_candles(), features=features)

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.BUY
    assert outcome.signals[0].reason == "momentum_atr_setup"


def test_swing_strategy_skips_entry_when_rsi_is_above_new_threshold() -> None:
    config = _build_config()
    strategy = SwingATRStrategy(config=config)
    context = AgentContext(config=config)
    context.available_cash_usd = 1_000.0
    features = FeatureSet(
        last_price=100.0,
        atr=2.0,
        rsi=44.0,
        ema_fast=105.0,
        ema_slow=100.0,
        macd_histogram=1.0,
    )

    outcome = strategy.generate(context=context, candles=_candles(), features=features)

    assert outcome.signals == []


def test_swing_strategy_generates_take_profit_sell_for_open_position() -> None:
    config = _build_config()
    strategy = SwingATRStrategy(config=config)
    context = AgentContext(config=config)
    context.active_swing_positions = [
        SwingPosition(
            position_id="paper-1",
            symbol="BTC-USD",
            entry_price=100.0,
            stop_loss=95.0,
            btc_units=1.0,
            size_usd=100.0,
            opened_at="2026-01-01T00:00:00+00:00",
        )
    ]
    features = FeatureSet(
        last_price=102.5,
        atr=1.0,
        rsi=50.0,
        ema_fast=103.0,
        ema_slow=101.0,
        macd_histogram=0.5,
    )

    outcome = strategy.generate(context=context, candles=_candles(5), features=features)

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.SELL
    assert outcome.signals[0].reason == "swing_take_profit:paper-1"


def test_swing_strategy_exits_when_no_follow_through_occurs() -> None:
    config = _build_config()
    strategy = SwingATRStrategy(config=config)
    context = AgentContext(config=config)
    context.active_swing_positions = [
        SwingPosition(
            position_id="paper-2",
            symbol="BTC-USD",
            entry_price=100.0,
            stop_loss=95.0,
            btc_units=1.0,
            size_usd=100.0,
            opened_at="2026-01-01T00:00:00+00:00",
        )
    ]
    features = FeatureSet(
        last_price=100.1,
        atr=1.0,
        rsi=40.0,
        ema_fast=101.0,
        ema_slow=100.0,
        macd_histogram=0.2,
    )

    outcome = strategy.generate(context=context, candles=_candles(5), features=features)

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.SELL
    assert outcome.signals[0].reason == "swing_no_follow_through:paper-2"
