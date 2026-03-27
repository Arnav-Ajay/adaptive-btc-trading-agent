# app/config/schema.py
"""Typed application configuration schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TradingConfig:
    """Trading-related configuration values."""

    symbol: str = "BTC-USD"
    dca_drop_percent: float = 3.0
    dca_order_size_usd: float = 100.0
    atr_multiplier: float = 2.0
    swing_entry_rsi_max: float = 35.0
    swing_take_profit_percent: float = 2.0
    swing_no_follow_through_candles: int = 3
    swing_follow_through_buffer_percent: float = 0.2
    max_drawdown_percent: float = 25.0


@dataclass(slots=True)
class DataConfig:
    """Local market data storage configuration."""

    data_lake_path: str = "data_lake"
    trading_lookback: int = 500
    dashboard_lookback: int = 20000
    min_candles_required: int = 50
    max_data_staleness_minutes: int = 90


@dataclass(slots=True)
class IngestionConfig:
    """Market data ingestion configuration."""

    provider: str = "coinbase"
    enabled: bool = True
    interval: str = "1m"
    schedule_minutes: int = 30
    overlap_minutes: int = 90
    fetch_limit: int = 300
    max_retries: int = 3
    retry_delay_seconds: int = 5
    state_path: str = "data_lake/state/coinbase_btc_usd_1m.json"
    health_max_staleness_minutes: int = 75


@dataclass(slots=True)
class RuntimeConfig:
    """Runtime behavior configuration."""

    loop_interval_seconds: int = 60
    max_cycles: int | None = 1
    schedule_minutes: int = 30
    decision_offset_minutes: int = 2
    health_max_staleness_minutes: int = 95


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
    execution_cost_preset: str = "simple"
    fee_pct: float = 0.001
    spread_pct: float = 0.0005
    slippage_pct: float = 0.0005
    paper_fee_bps: float = 0.0
    paper_state_path: str = "data_lake/state/paper_broker_state.json"
    paper_trade_log_path: str = "data_lake/state/paper_trade_ledger.jsonl"
    paper_cycle_log_path: str = "data_lake/state/paper_cycle_log.jsonl"
    paper_snapshot_path: str = "data_lake/state/paper_portfolio_snapshot.json"
    paper_decision_trace_path: str = "data_lake/state/paper_decision_trace.jsonl"


@dataclass(slots=True)
class AppConfig:
    """Top-level application configuration container."""

    trading: TradingConfig
    data: DataConfig
    ingestion: IngestionConfig
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
            data=DataConfig(**data.get("data", {})),
            ingestion=IngestionConfig(**data.get("ingestion", {})),
            runtime=RuntimeConfig(**data.get("runtime", {})),
            logging=LoggingConfig(**data.get("logging", {})),
            notifications=NotificationConfig(**data.get("notifications", {})),
            llm=LLMConfig(**data.get("llm", {})),
            execution=ExecutionConfig(**data.get("execution", {})),
            env=data.get("env", {}),
            cache_path=data.get("cache_path", "config/config_cache.json"),
        )
