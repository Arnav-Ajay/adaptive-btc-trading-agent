"""Gmail reporting client."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config.schema import AppConfig


logger = logging.getLogger(__name__)


class GmailReporter:
    """Send weekly summary emails when enabled."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the Gmail reporter from environment-backed configuration."""
        self.config = config

    def send_weekly_report(self, subject: str, html_body: str) -> bool:
        """Send an HTML weekly report using Gmail SMTP or log a noop when disabled."""
        if not self.config.notifications.gmail_enabled:
            logger.info("Gmail report skipped because gmail notifications are disabled: %s", subject)
            return False

        username = self.config.env.get("GMAIL_USERNAME", "").strip()
        app_password = self.config.env.get("GMAIL_APP_PASSWORD", "").strip()
        recipient = self.config.env.get("GMAIL_TO", "").strip()
        if not username or not app_password or not recipient:
            logger.warning("Gmail report skipped because Gmail SMTP credentials or recipient are missing")
            return False

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = username
        message["To"] = recipient
        message.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(username, app_password)
                smtp.sendmail(
                    username,
                    [item.strip() for item in recipient.split(",") if item.strip()],
                    message.as_string(),
                )
        except Exception as exc:
            logger.exception("Gmail weekly report failed: %s", exc)
            return False
        logger.info("Gmail weekly report sent successfully: %s", subject)
        return True

