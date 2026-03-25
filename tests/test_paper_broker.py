"""Tests for persisted paper broker behavior."""

from __future__ import annotations

from pathlib import Path

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
    assert snapshot.cash_usd == 900.0
    assert snapshot.btc_units > 0
    assert reloaded.latest_buy_price() == 50_000.0
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
    assert len(broker.active_swing_positions()) == 0
