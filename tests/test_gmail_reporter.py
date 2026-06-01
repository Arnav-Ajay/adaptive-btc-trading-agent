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
from app.monitoring.gmail import GmailReporter


def _config(*, gmail_enabled: bool, env: dict[str, str]) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(gmail_enabled=gmail_enabled),
        llm=LLMConfig(),
        execution=ExecutionConfig(),
        env=env,
        cache_path="",
    )


def test_gmail_reporter_skips_when_disabled() -> None:
    """Disabled Gmail notifications should short-circuit without sending."""
    reporter = GmailReporter(_config(gmail_enabled=False, env={}))
    assert reporter.send_weekly_report("subject", "<html></html>") is False


def test_gmail_reporter_sends_html_via_smtp(monkeypatch) -> None:
    """Gmail reporter should use STARTTLS SMTP and send an HTML message."""
    events: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int):
            events["host"] = host
            events["port"] = port
            events["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            events["starttls"] = True

        def login(self, username: str, password: str):
            events["login"] = (username, password)

        def sendmail(self, sender: str, recipients: list[str], message: str):
            events["sendmail"] = (sender, recipients, message)

    monkeypatch.setattr("app.monitoring.gmail.smtplib.SMTP", FakeSMTP)
    reporter = GmailReporter(
        _config(
            gmail_enabled=True,
            env={
                "GMAIL_USERNAME": "sender@example.com",
                "GMAIL_APP_PASSWORD": "app-password",
                "GMAIL_TO": "recipient@example.com",
            },
        )
    )

    sent = reporter.send_weekly_report("Weekly", "<html><body>hello</body></html>")

    assert sent is True
    assert events["host"] == "smtp.gmail.com"
    assert events["port"] == 587
    assert events["starttls"] is True
    assert events["login"] == ("sender@example.com", "app-password")
    sender, recipients, message = events["sendmail"]
    assert sender == "sender@example.com"
    assert recipients == ["recipient@example.com"]
    assert "Content-Type: text/html" in message
    assert "Weekly" in message
