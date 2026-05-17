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
from app.strategies.pullback_trend import PullbackTrendStrategy
from app.utils.models import AgentContext, Candle, FeatureSet, MarketRegime, SwingPosition, TradeSide


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


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return [
        Candle(
            timestamp=start + timedelta(minutes=index),
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]


def test_pullback_strategy_generates_entry_in_bullish_retracement() -> None:
    config = _build_config()
    strategy = PullbackTrendStrategy(config=config)
    context = AgentContext(config=config)
    context.available_cash_usd = 1_000.0
    context.market_regime = MarketRegime.BULLISH
    candles = _candles(
        [
            100, 102, 104, 108, 112, 108, 104,
            106, 110, 116, 122, 118, 114,
            116, 120, 126, 132, 128, 124,
            125, 126, 127,
        ]
    )
    features = FeatureSet(
        last_price=127.0,
        atr=2.0,
        rsi=54.0,
        ema_fast=126.0,
        ema_slow=120.0,
        macd_histogram=0.5,
    )

    outcome = strategy.generate(context=context, candles=candles, features=features)

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.BUY
    assert outcome.signals[0].reason == "pullback_trend_entry"
    assert outcome.signals[0].strategy_name == "PullbackTrendStrategy"


def test_pullback_strategy_blocks_entry_outside_bullish_regime() -> None:
    config = _build_config()
    strategy = PullbackTrendStrategy(config=config)
    context = AgentContext(config=config)
    context.available_cash_usd = 1_000.0
    context.market_regime = MarketRegime.SIDEWAYS
    candles = _candles([100, 102, 104, 108, 112, 108, 104, 106, 110, 116, 122, 118, 114, 116, 120, 126, 132, 128, 124, 125, 126, 127])
    features = FeatureSet(
        last_price=127.0,
        atr=2.0,
        rsi=54.0,
        ema_fast=126.0,
        ema_slow=120.0,
        macd_histogram=0.5,
    )

    outcome = strategy.generate(context=context, candles=candles, features=features)

    assert outcome.signals == []
    assert "skip:pullback_regime_blocked" in outcome.trace


def test_pullback_strategy_generates_take_profit_sell_for_owned_position() -> None:
    config = _build_config()
    strategy = PullbackTrendStrategy(config=config)
    context = AgentContext(config=config)
    context.active_swing_positions = [
        SwingPosition(
            position_id="pullback-1",
            symbol="BTC-USD",
            entry_price=100.0,
            stop_loss=95.0,
            btc_units=1.0,
            size_usd=100.0,
            opened_at="2026-01-01T00:00:00+00:00",
            strategy_name="PullbackTrendStrategy",
        )
    ]
    candles = _candles([100.0, 101.0, 103.0, 106.0, 111.0])
    features = FeatureSet(
        last_price=111.0,
        atr=1.0,
        rsi=60.0,
        ema_fast=110.0,
        ema_slow=106.0,
        macd_histogram=0.4,
    )

    outcome = strategy.generate(context=context, candles=candles, features=features)

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.SELL
    assert outcome.signals[0].reason == "pullback_take_profit:pullback-1"


def test_pullback_strategy_does_not_require_rsi_or_macd_entry_filters() -> None:
    config = _build_config()
    strategy = PullbackTrendStrategy(config=config)
    context = AgentContext(config=config)
    context.available_cash_usd = 1_000.0
    context.market_regime = MarketRegime.BULLISH
    candles = _candles(
        [
            100, 102, 104, 108, 112, 108, 104,
            106, 110, 116, 122, 118, 114,
            116, 120, 126, 132, 128, 124,
            123, 124, 126,
        ]
    )
    features = FeatureSet(
        last_price=126.0,
        atr=2.0,
        rsi=35.0,
        ema_fast=118.0,
        ema_slow=121.0,
        macd_histogram=-0.4,
    )

    outcome = strategy.generate(context=context, candles=candles, features=features)

    assert len(outcome.signals) == 1
    assert outcome.signals[0].reason == "pullback_trend_entry"


def test_pullback_signal_exit_requires_both_ema_and_macd_breakdown() -> None:
    config = _build_config()
    strategy = PullbackTrendStrategy(config=config)
    context = AgentContext(config=config)
    context.active_swing_positions = [
        SwingPosition(
            position_id="pullback-2",
            symbol="BTC-USD",
            entry_price=100.0,
            stop_loss=95.0,
            btc_units=1.0,
            size_usd=100.0,
            opened_at="2026-01-01T00:00:00+00:00",
            strategy_name="PullbackTrendStrategy",
        )
    ]
    candles = _candles([100.0, 101.0, 102.0, 103.0, 104.0])
    features = FeatureSet(
        last_price=104.0,
        atr=1.0,
        rsi=55.0,
        ema_fast=103.0,
        ema_slow=105.0,
        macd_histogram=0.2,
    )

    outcome = strategy.generate(context=context, candles=candles, features=features)

    assert outcome.signals == []
    assert "hold:pullback_position position_id=pullback-2" in outcome.trace
