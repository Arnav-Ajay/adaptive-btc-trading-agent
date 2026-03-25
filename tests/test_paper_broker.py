"""Tests for persisted paper broker behavior."""

from __future__ import annotations

from pathlib import Path

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
from app.execution.paper_broker import PaperBroker
from app.utils.models import OrderRequest, TradeSide


def _build_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(data_lake_path=str(tmp_path)),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(),
        execution=ExecutionConfig(
            initial_cash_usd=1_000.0,
            execution_cost_preset="custom",
            fee_pct=0.001,
            spread_pct=0.0005,
            slippage_pct=0.0005,
            paper_state_path=str(tmp_path / "paper_state.json"),
            paper_trade_log_path=str(tmp_path / "paper_ledger.jsonl"),
        ),
        env={},
        cache_path="",
    )


def test_paper_broker_persists_state_and_ledger(tmp_path) -> None:
    """Paper broker should persist balances and append fills."""
    config = _build_config(tmp_path)
    broker = PaperBroker(config)
    result = broker.place_order(
        OrderRequest(side=TradeSide.BUY, symbol="BTC-USD", size_usd=100.0, price=50_000.0)
    )
    assert result.accepted is True

    reloaded = PaperBroker(config)
    snapshot = reloaded.get_portfolio_snapshot()
    assert snapshot.cash_usd == pytest.approx(900.0)
    assert snapshot.btc_units > 0
    assert reloaded.latest_buy_price() == pytest.approx(50_050.0)
    assert snapshot.total_fees_usd == pytest.approx(0.1)
    assert snapshot.total_spread_cost_usd == pytest.approx(0.05)
    assert snapshot.total_slippage_cost_usd == pytest.approx(0.05)
    assert (tmp_path / "paper_ledger.jsonl").exists()


def test_paper_broker_closes_swing_position_on_stop_loss(tmp_path) -> None:
    """Swing positions should be closed automatically once the stop-loss is breached."""
    config = _build_config(tmp_path)
    broker = PaperBroker(config)
    buy_result = broker.place_order(
        OrderRequest(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=200.0,
            price=50_000.0,
            reason="momentum_atr_setup",
            stop_loss=49_000.0,
            strategy_name="SwingATRStrategy",
        )
    )
    assert buy_result.accepted is True
    assert len(broker.active_swing_positions()) == 1

    broker.mark_price(48_500.0)
    stop_results = broker.evaluate_stop_losses()
    assert len(stop_results) == 1
    assert stop_results[0].accepted is True
    assert stop_results[0].side is TradeSide.SELL
    assert stop_results[0].fee_usd > 0
    assert stop_results[0].realized_pnl_usd is not None
    assert len(broker.active_swing_positions()) == 0


def test_paper_broker_tracks_realized_pnl_for_closed_swing_trade(tmp_path) -> None:
    """Closed swing trades should accumulate realized PnL and fees in the snapshot."""
    config = _build_config(tmp_path)
    broker = PaperBroker(config)
    buy_result = broker.place_order(
        OrderRequest(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=200.0,
            price=50_000.0,
            reason="momentum_atr_setup",
            stop_loss=49_000.0,
            strategy_name="SwingATRStrategy",
        )
    )
    assert buy_result.accepted is True

    sell_result = broker.place_order(
        OrderRequest(
            side=TradeSide.SELL,
            symbol="BTC-USD",
            size_usd=220.0,
            price=55_000.0,
            reason=f"stop_loss_hit:{buy_result.order_id}",
            strategy_name="SwingATRStrategy",
        )
    )
    assert sell_result.accepted is True
    assert sell_result.realized_pnl_usd is not None
    snapshot = broker.get_portfolio_snapshot()
    assert snapshot.realized_pnl_usd == sell_result.realized_pnl_usd
    assert snapshot.total_fees_usd > 0
    assert snapshot.total_spread_cost_usd > 0
    assert snapshot.total_slippage_cost_usd > 0


def test_latest_buy_price_uses_most_recent_buy_fill_across_strategies(tmp_path) -> None:
    """The latest buy context should reflect the newest buy, even if it was a swing entry."""
    config = _build_config(tmp_path)
    broker = PaperBroker(config)
    first_buy = broker.place_order(
        OrderRequest(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=100.0,
            price=70_719.09,
            reason="initial_dca_entry",
            strategy_name="DCAStrategy",
        )
    )
    assert first_buy.accepted is True

    second_buy = broker.place_order(
        OrderRequest(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=250.0,
            price=70_849.20,
            reason="momentum_atr_setup",
            stop_loss=70_762.49,
            strategy_name="SwingATRStrategy",
        )
    )
    assert second_buy.accepted is True
    assert broker.latest_buy_price() == pytest.approx(70_920.0492)
