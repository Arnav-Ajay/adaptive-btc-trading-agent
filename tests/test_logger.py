"""Tests for logging configuration."""

from __future__ import annotations

from pathlib import Path

from app.monitoring.logger import configure_logging
import logging


def test_configure_logging_creates_service_log_file(tmp_path, monkeypatch) -> None:
    """Service-specific logging should create a file-backed log handler."""
    monkeypatch.chdir(tmp_path)
    configure_logging("INFO", service_name="ingestion")
    logger = logging.getLogger("test.ingestion")
    logger.info("hello ingestion log")

    log_file = Path("logs") / "ingestion" / "ingestion.log"
    assert log_file.exists()
    assert "hello ingestion log" in log_file.read_text(encoding="utf-8")
