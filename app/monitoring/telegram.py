"""Telegram notification client."""

from __future__ import annotations

import logging
import json
from urllib import error, parse, request

from app.config.schema import AppConfig


logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send Telegram alerts when enabled."""

    API_TIMEOUT_SECONDS = 10

    def __init__(self, config: AppConfig) -> None:
        """Initialize the Telegram client from environment-backed config."""
        self.config = config
        self.enabled = bool(config.notifications.telegram_enabled)
        self.bot_token = config.env.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = config.env.get("TELEGRAM_CHAT_ID", "").strip()

    def send(self, message: str) -> bool:
        """Send a Telegram message via the Bot API."""
        if not self.enabled:
            logger.info("Telegram notification skipped because telegram notifications are disabled")
            return False
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram notification skipped because bot token or chat id is missing")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        http_request = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.API_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            response_body = ""
            try:
                response_body = exc.read().decode("utf-8")
            except OSError:
                response_body = ""
            logger.error(
                "Telegram notification failed: http_status=%s reason=%s response=%s",
                exc.code,
                exc.reason,
                response_body or "<empty>",
            )
            return False
        except (error.URLError, TimeoutError, OSError):
            logger.exception("Telegram notification failed")
            return False

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Telegram notification failed with non-JSON response: %s", body)
            return False
        if not parsed.get("ok", False):
            logger.warning("Telegram notification rejected by API: %s", parsed)
            return False
        logger.info("Telegram notification sent successfully")
        return True

