"""Telegram notification client."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send Telegram alerts when enabled."""

    def send(self, message: str) -> None:
        """Send a Telegram message or log a noop in development."""
        logger.info("Telegram notification skipped: %s", message)

