"""Notification orchestration."""

from __future__ import annotations

import logging

from app.config.schema import AppConfig
from app.monitoring.gmail import GmailReporter
from app.monitoring.telegram import TelegramNotifier
from app.monitoring.weekly_report import WeeklyReport, build_weekly_report
from app.utils.models import OrderResult, PortfolioSnapshot, TradeSide


logger = logging.getLogger(__name__)


class NotificationManager:
    """Fan out event notifications to configured channels."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the notification manager."""
        self.config = config
        self.telegram = TelegramNotifier(config=config)
        self.gmail = GmailReporter(config=config)

    def notify_cycle(
        self,
        cycle: int,
        regime: str,
        signal_count: int,
        execution_results: list[OrderResult],
        summary: str,
    ) -> None:
        """Emit cycle-level status notifications."""
        message = (
            f"cycle={cycle} regime={regime} signals={signal_count} "
            f"executions={len(execution_results)} summary={summary}"
        )
        logger.info("Notification payload: %s", message)

    def notify_trade_fills(
        self,
        *,
        decision_owner_strategy: str,
        execution_results: list[OrderResult],
        snapshot: PortfolioSnapshot,
    ) -> None:
        """Emit one Telegram message per accepted paper-trade fill."""
        if not self.config.notifications.telegram_enabled:
            return

        for result in execution_results:
            if not result.accepted or result.side not in {TradeSide.BUY, TradeSide.SELL}:
                continue
            self.telegram.send(self._format_trade_message(decision_owner_strategy=decision_owner_strategy, result=result, snapshot=snapshot))

    @staticmethod
    def _format_trade_message(
        *,
        decision_owner_strategy: str,
        result: OrderResult,
        snapshot: PortfolioSnapshot,
    ) -> str:
        """Render a single executed fill as a Telegram message."""
        side = "🟢 BUY" if result.side is TradeSide.BUY else "🔴 SELL"
        return "\n".join(
            [
                side,
                "",
                f"Decision Owner: {decision_owner_strategy}",
                f"Execution Source: {result.strategy_name or 'n/a'}",
                f"Price: ${result.price:,.2f}",
                f"Size USD: ${result.size_usd:,.2f}",
                f"BTC Units: {result.size_usd / result.price:.6f} BTC" if result.price > 0 else "BTC Units: 0.000000 BTC",
                f"Reason: {result.reason}",
                "",
                "Portfolio:",
                f"Cash: ${snapshot.cash_usd:,.2f}",
                f"BTC Holdings: {snapshot.btc_units:.6f} BTC",
                f"Equity: ${snapshot.equity_usd:,.2f}",
            ]
        )

    def build_weekly_report(self, now=None) -> WeeklyReport:
        """Build the weekly HTML report from persisted artifacts."""
        return build_weekly_report(self.config, now=now)

    def send_weekly_report(self, now=None) -> bool:
        """Build and send the weekly HTML report via Gmail."""
        report = self.build_weekly_report(now=now)
        return self.gmail.send_weekly_report(report.subject, report.html)
