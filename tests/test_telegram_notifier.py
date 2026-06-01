from __future__ import annotations

import json
from urllib.error import HTTPError

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
from app.monitoring.telegram import TelegramNotifier


def _config(*, telegram_enabled: bool, env: dict[str, str]) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(telegram_enabled=telegram_enabled),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env=env,
        cache_path="",
    )


def test_telegram_notifier_skips_when_disabled() -> None:
    """Disabled Telegram notifications should short-circuit without sending."""
    notifier = TelegramNotifier(_config(telegram_enabled=False, env={}))
    assert notifier.send("hello") is False


def test_telegram_notifier_skips_when_credentials_missing() -> None:
    """Missing Telegram credentials should short-circuit without sending."""
    notifier = TelegramNotifier(_config(telegram_enabled=True, env={}))
    assert notifier.send("hello") is False


def test_telegram_notifier_posts_via_bot_api(monkeypatch) -> None:
    """Telegram notifier should post the message to the Bot API."""
    events: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"ok": True, "result": {"message_id": 1}}).encode("utf-8")

    def fake_urlopen(req, timeout: int):
        events["url"] = req.full_url
        events["method"] = req.get_method()
        events["headers"] = dict(req.header_items())
        events["data"] = req.data.decode("utf-8")
        events["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.monitoring.telegram.request.urlopen", fake_urlopen)
    notifier = TelegramNotifier(
        _config(
            telegram_enabled=True,
            env={
                "TELEGRAM_BOT_TOKEN": "bot-token",
                "TELEGRAM_CHAT_ID": "chat-123",
            },
        )
    )

    sent = notifier.send("Trade fill")

    assert sent is True
    assert events["url"] == "https://api.telegram.org/botbot-token/sendMessage"
    assert events["method"] == "POST"
    assert events["timeout"] == 10
    assert "chat_id=chat-123" in str(events["data"])
    assert "text=Trade+fill" in str(events["data"])


def test_telegram_notifier_handles_api_rejection(monkeypatch) -> None:
    """Telegram API rejections should return False without raising."""
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"ok": False, "description": "Bad Request"}).encode("utf-8")

    monkeypatch.setattr("app.monitoring.telegram.request.urlopen", lambda req, timeout: FakeResponse())
    notifier = TelegramNotifier(
        _config(
            telegram_enabled=True,
            env={
                "TELEGRAM_BOT_TOKEN": "bot-token",
                "TELEGRAM_CHAT_ID": "chat-123",
            },
        )
    )

    assert notifier.send("Trade fill") is False


def test_telegram_notifier_handles_http_error_with_response_body(monkeypatch) -> None:
    """HTTP errors should return False and consume the Telegram response body."""
    def fake_urlopen(req, timeout: int):
        raise HTTPError(
            req.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("app.monitoring.telegram.request.urlopen", fake_urlopen)
    notifier = TelegramNotifier(
        _config(
            telegram_enabled=True,
            env={
                "TELEGRAM_BOT_TOKEN": "bot-token",
                "TELEGRAM_CHAT_ID": "chat-123",
            },
        )
    )

    assert notifier.send("Trade fill") is False
