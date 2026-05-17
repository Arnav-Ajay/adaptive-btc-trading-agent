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
from app.strategies.dca import DCAStrategy
from app.utils.models import AgentContext, FeatureSet, MarketRegime, PortfolioSnapshot, TradeSide


def _build_config(**trading_overrides: float | bool) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(**trading_overrides),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(initial_cash_usd=1_000.0),
        env={},
        cache_path="",
    )


def _context(config: AppConfig, *, regime: MarketRegime, cash_usd: float, btc_units: float) -> AgentContext:
    context = AgentContext(config=config)
    context.market_regime = regime
    context.available_cash_usd = cash_usd
    context.portfolio_snapshot = PortfolioSnapshot(
        cash_usd=cash_usd,
        btc_units=btc_units,
        equity_usd=cash_usd + (btc_units * 100.0),
        drawdown_percent=0.0,
        last_mark_price=100.0,
    )
    return context


def _features(last_price: float = 100.0) -> FeatureSet:
    return FeatureSet(last_price=last_price)


def test_dca_strategy_blocks_new_entries_in_bearish_regime_by_default() -> None:
    config = _build_config()
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.BEARISH, cash_usd=1_000.0, btc_units=0.0)

    outcome = strategy.generate(context=context, candles=[], features=_features())

    assert outcome.signals == []
    assert "skip:dca_regime_blocked" in outcome.trace


def test_dca_strategy_scales_order_size_in_weakening_bull() -> None:
    config = _build_config(dca_order_size_usd=100.0, dca_weakening_bull_size_multiplier=0.5)
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.WEAKENING_BULL, cash_usd=1_000.0, btc_units=0.0)

    outcome = strategy.generate(context=context, candles=[], features=_features())

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.BUY
    assert outcome.signals[0].size_usd == 50.0


def test_dca_strategy_blocks_entry_when_btc_allocation_cap_is_reached() -> None:
    config = _build_config(max_btc_allocation_percent=70.0)
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.BULLISH, cash_usd=200.0, btc_units=8.0)

    outcome = strategy.generate(context=context, candles=[], features=_features())

    assert outcome.signals == []
    assert "skip:btc_allocation_cap_reached" in outcome.trace


def test_dca_strategy_caps_order_size_to_remaining_btc_allocation_headroom() -> None:
    config = _build_config(dca_order_size_usd=100.0, max_btc_allocation_percent=70.0)
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.BULLISH, cash_usd=400.0, btc_units=6.8)

    outcome = strategy.generate(context=context, candles=[], features=_features())

    assert len(outcome.signals) == 1
    assert outcome.signals[0].size_usd == 76.0


def test_dca_strategy_rebalances_base_position_in_bearish_regime() -> None:
    config = _build_config(
        bearish_target_allocation_percent=15.0,
        rebalance_tolerance_percent=2.5,
        rebalance_max_sell_fraction=0.5,
    )
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.BEARISH, cash_usd=200.0, btc_units=8.0)
    context.portfolio_snapshot.dca_btc_units = 8.0

    outcome = strategy.generate(context=context, candles=[], features=_features())

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.SELL
    assert outcome.signals[0].reason == "dca_rebalance_sell:bearish"
    assert outcome.signals[0].size_usd == 400.0


def test_dca_strategy_rebalances_toward_weaker_target_in_weakening_bull() -> None:
    config = _build_config(
        weakening_bull_target_allocation_percent=35.0,
        rebalance_tolerance_percent=2.5,
        rebalance_max_sell_fraction=1.0,
    )
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.WEAKENING_BULL, cash_usd=400.0, btc_units=8.0)
    context.portfolio_snapshot.dca_btc_units = 8.0

    outcome = strategy.generate(context=context, candles=[], features=_features())

    assert len(outcome.signals) == 1
    assert outcome.signals[0].side is TradeSide.SELL
    assert outcome.signals[0].reason == "dca_rebalance_sell:weakening_bull"
    assert outcome.signals[0].size_usd == 380.0


def test_dca_threshold_not_changed_by_swing_buy() -> None:
    config = _build_config(dca_drop_percent=10.0, dca_order_size_usd=100.0)
    strategy = DCAStrategy(config=config)
    context = _context(config, regime=MarketRegime.BULLISH, cash_usd=1_000.0, btc_units=0.0)
    context.latest_buy_fill_price = 200.0
    context.latest_dca_buy_price = 100.0

    outcome = strategy.generate(context=context, candles=[], features=_features(last_price=150.0))

    assert outcome.signals == []
    assert any("latest_dca_buy_price=100.00" in item for item in outcome.trace)
