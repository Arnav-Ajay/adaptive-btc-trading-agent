# app/monitoring/logger.py
"""Logging setup."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def configure_logging(level: str, service_name: str | None = None) -> None:
    """Configure application-wide logging with optional service-specific file output."""
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    for handler in handlers:
        handler.setFormatter(formatter)

    if service_name:
        log_dir = Path("logs") / service_name
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename=log_dir / f"{service_name}.log",
            when="midnight",
            interval=1,
            backupCount=14,
            encoding="utf-8",
            utc=True,
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(level=resolved_level, handlers=handlers, force=True)
