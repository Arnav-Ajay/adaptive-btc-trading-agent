"""Notification orchestration."""

from __future__ import annotations

import logging

from app.config.schema import AppConfig
from app.monitoring.gmail import GmailReporter
from app.monitoring.telegram import TelegramNotifier
from app.utils.models import OrderResult


logger = logging.getLogger(__name__)


class NotificationManager:
    """Fan out event notifications to configured channels."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the notification manager."""
        self.config = config
        self.telegram = TelegramNotifier()
        self.gmail = GmailReporter()

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
        if self.config.notifications.telegram_enabled:
            self.telegram.send(message)
