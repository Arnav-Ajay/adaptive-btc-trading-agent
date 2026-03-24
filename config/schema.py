"""Typed application configuration schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TradingConfig:
    """Trading-related configuration values."""

    symbol: str = "BTC-USD"
    interval: str = "1h"
    dca_drop_percent: float = 3.0
    dca_order_size_usd: float = 100.0
    atr_multiplier: float = 2.0
    max_drawdown_percent: float = 25.0


@dataclass(slots=True)
class RuntimeConfig:
    """Runtime behavior configuration."""

    loop_interval_seconds: int = 60
    max_cycles: int | None = 1


@dataclass(slots=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"


@dataclass(slots=True)
class NotificationConfig:
    """Notification channel configuration."""

    telegram_enabled: bool = False
    gmail_enabled: bool = False


@dataclass(slots=True)
class LLMConfig:
    """LLM advisory configuration."""

    enabled: bool = False
    model: str = "gpt-5.4-mini"


@dataclass(slots=True)
class ExecutionConfig:
    """Execution and brokerage configuration."""

    paper_trading_enabled: bool = True
    initial_cash_usd: float = 10_000.0


@dataclass(slots=True)
class AppConfig:
    """Top-level application configuration container."""

    trading: TradingConfig
    runtime: RuntimeConfig
    logging: LoggingConfig
    notifications: NotificationConfig
    llm: LLMConfig
    execution: ExecutionConfig
    env: dict[str, str]
    cache_path: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppConfig":
        """Create a validated config object from a nested mapping."""
        return cls(
            trading=TradingConfig(**data.get("trading", {})),
            runtime=RuntimeConfig(**data.get("runtime", {})),
            logging=LoggingConfig(**data.get("logging", {})),
            notifications=NotificationConfig(**data.get("notifications", {})),
            llm=LLMConfig(**data.get("llm", {})),
            execution=ExecutionConfig(**data.get("execution", {})),
            env=data.get("env", {}),
            cache_path=data.get("cache_path", "config/config_cache.json"),
        )
