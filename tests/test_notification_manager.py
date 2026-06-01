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
from app.monitoring.alerts import NotificationManager
from app.utils.models import OrderResult, PortfolioSnapshot, TradeSide


def _config(*, telegram_enabled: bool) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(telegram_enabled=telegram_enabled),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env={},
        cache_path="",
    )


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        cash_usd=9_875.0,
        btc_units=0.001691,
        equity_usd=9_999.86,
        drawdown_percent=0.0,
        avg_entry_price=73_920.9,
        last_mark_price=73_836.61,
        dca_btc_units=0.001691,
        swing_btc_units=0.0,
        realized_pnl_usd=0.0,
        total_fees_usd=0.12,
        total_spread_cost_usd=0.06,
        total_slippage_cost_usd=0.06,
    )


def test_notification_manager_sends_one_message_per_accepted_fill(monkeypatch) -> None:
    """Accepted buy and sell fills should each produce one Telegram message."""
    manager = NotificationManager(config=_config(telegram_enabled=True))
    sent_messages: list[str] = []
    monkeypatch.setattr(manager.telegram, "send", lambda message: sent_messages.append(message) or True)

    manager.notify_trade_fills(
        decision_owner_strategy="HybridStrategy",
        execution_results=[
            OrderResult(
                accepted=True,
                order_id="paper-1",
                reason="initial_dca_entry",
                side=TradeSide.BUY,
                symbol="BTC-USD",
                size_usd=125.0,
                price=73_846.98,
                strategy_name="DCAStrategy",
            ),
            OrderResult(
                accepted=False,
                order_id="",
                reason="duplicate_signal_blocked",
                side=TradeSide.BUY,
                symbol="BTC-USD",
                size_usd=125.0,
                price=73_846.98,
                strategy_name="DCAStrategy",
            ),
            OrderResult(
                accepted=True,
                order_id="paper-2",
                reason="swing_take_profit:paper-0",
                side=TradeSide.SELL,
                symbol="BTC-USD",
                size_usd=130.0,
                price=75_000.0,
                strategy_name="SwingATRStrategy",
                realized_pnl_usd=5.0,
            ),
        ],
        snapshot=_snapshot(),
    )

    assert len(sent_messages) == 2
    assert "🟢 BUY" in sent_messages[0]
    assert "Decision Owner: HybridStrategy" in sent_messages[0]
    assert "Execution Source: DCAStrategy" in sent_messages[0]
    assert "BTC Units: 0.001693 BTC" in sent_messages[0]
    assert "Reason: initial_dca_entry" in sent_messages[0]
    assert "🔴 SELL" in sent_messages[1]
    assert "Execution Source: SwingATRStrategy" in sent_messages[1]


def test_notification_manager_formats_stop_loss_exit_with_portfolio() -> None:
    """Stop-loss exits should report the stop-loss decision owner and portfolio summary."""
    message = NotificationManager._format_trade_message(
        decision_owner_strategy="StopLossExit",
        result=OrderResult(
            accepted=True,
            order_id="paper-3",
            reason="stop_loss_hit:paper-2",
            side=TradeSide.SELL,
            symbol="BTC-USD",
            size_usd=118.5,
            price=71_000.0,
            strategy_name="SwingATRStrategy",
            stop_loss=71_500.0,
        ),
        snapshot=_snapshot(),
    )

    assert "🔴 SELL" in message
    assert "Decision Owner: StopLossExit" in message
    assert "Execution Source: SwingATRStrategy" in message
    assert "Price: $71,000.00" in message
    assert "Size USD: $118.50" in message
    assert "BTC Units: 0.001669 BTC" in message
    assert "Cash: $9,875.00" in message
    assert "BTC Holdings: 0.001691 BTC" in message
    assert "Equity: $9,999.86" in message
