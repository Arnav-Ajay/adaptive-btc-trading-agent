"""Gmail reporting client."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class GmailReporter:
    """Send weekly summary emails when enabled."""

    def send_weekly_report(self, subject: str, body: str) -> None:
        """Send a weekly report or log a noop in development."""
        logger.info("Gmail report skipped: %s", subject)
        logger.debug("Weekly report body: %s", body)

