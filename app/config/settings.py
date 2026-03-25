# app/config/settings.py
"""Configuration loading helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config.schema import AppConfig
from app.config.sheet_loader import GoogleSheetConfigLoader
from app.execution.cost_model import resolve_execution_costs


def _load_env() -> dict[str, Any]:
    """Load dotenv-style environment variables if available."""
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    return dict(os.environ)


def _load_local_cache(path: Path) -> dict[str, Any]:
    """Load the local JSON configuration cache."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    """Parse a boolean environment variable."""
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_optional_int(raw_value: str | None, default: int | None) -> int | None:
    """Parse an optional integer environment variable."""
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def _apply_env_overrides(base_config: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
    """Overlay supported environment variables onto nested config data."""
    trading = dict(base_config.get("trading", {}))
    data = dict(base_config.get("data", {}))
    ingestion = dict(base_config.get("ingestion", {}))
    runtime = dict(base_config.get("runtime", {}))
    logging = dict(base_config.get("logging", {}))
    notifications = dict(base_config.get("notifications", {}))
    llm = dict(base_config.get("llm", {}))
    execution = dict(base_config.get("execution", {}))

    trading["symbol"] = env.get("TRADING_SYMBOL", trading.get("symbol", "BTC-USD"))

    data["data_lake_path"] = env.get("DATA_LAKE_PATH", data.get("data_lake_path", "data_lake"))
    data["trading_lookback"] = int(env.get("TRADING_LOOKBACK", data.get("trading_lookback", 500)))
    data["dashboard_lookback"] = int(
        env.get("DASHBOARD_LOOKBACK", data.get("dashboard_lookback", 20000))
    )
    data["min_candles_required"] = int(
        env.get("MIN_CANDLES_REQUIRED", data.get("min_candles_required", 50))
    )
    data["max_data_staleness_minutes"] = int(
        env.get("MAX_DATA_STALENESS_MINUTES", data.get("max_data_staleness_minutes", 90))
    )

    ingestion["provider"] = env.get("INGESTION_PROVIDER", ingestion.get("provider", "coinbase"))
    ingestion["enabled"] = _parse_bool(env.get("INGESTION_ENABLED"), ingestion.get("enabled", True))
    ingestion["interval"] = env.get("INGESTION_INTERVAL", ingestion.get("interval", "1m"))
    ingestion["schedule_minutes"] = int(
        env.get("INGESTION_SCHEDULE_MINUTES", ingestion.get("schedule_minutes", 30))
    )
    ingestion["overlap_minutes"] = int(
        env.get("INGESTION_OVERLAP_MINUTES", ingestion.get("overlap_minutes", 90))
    )
    ingestion["fetch_limit"] = int(env.get("INGESTION_FETCH_LIMIT", ingestion.get("fetch_limit", 300)))
    ingestion["max_retries"] = int(env.get("INGESTION_MAX_RETRIES", ingestion.get("max_retries", 3)))
    ingestion["retry_delay_seconds"] = int(
        env.get("INGESTION_RETRY_DELAY_SECONDS", ingestion.get("retry_delay_seconds", 5))
    )
    ingestion["state_path"] = env.get(
        "INGESTION_STATE_PATH",
        ingestion.get("state_path", "data_lake/state/coinbase_btc_usd_1m.json"),
    )
    ingestion["health_max_staleness_minutes"] = int(
        env.get(
            "INGESTION_HEALTH_MAX_STALENESS_MINUTES",
            ingestion.get("health_max_staleness_minutes", 75),
        )
    )

    runtime["loop_interval_seconds"] = int(
        env.get("LOOP_INTERVAL_SECONDS", runtime.get("loop_interval_seconds", 60))
    )
    runtime["max_cycles"] = _parse_optional_int(
        env.get("MAX_CYCLES"),
        runtime.get("max_cycles", 1),
    )
    runtime["schedule_minutes"] = int(
        env.get("RUNTIME_SCHEDULE_MINUTES", runtime.get("schedule_minutes", 30))
    )
    runtime["decision_offset_minutes"] = int(
        env.get("RUNTIME_DECISION_OFFSET_MINUTES", runtime.get("decision_offset_minutes", 2))
    )
    runtime["health_max_staleness_minutes"] = int(
        env.get(
            "RUNTIME_HEALTH_MAX_STALENESS_MINUTES",
            runtime.get("health_max_staleness_minutes", 95),
        )
    )

    logging["level"] = env.get("LOG_LEVEL", logging.get("level", "INFO"))
    llm["model"] = env.get("OPENAI_MODEL", llm.get("model", "gpt-5.4-mini"))
    llm["enabled"] = _parse_bool(env.get("LLM_ENABLED"), llm.get("enabled", False))

    notifications["telegram_enabled"] = _parse_bool(
        env.get("TELEGRAM_ENABLED"),
        notifications.get("telegram_enabled", False),
    )
    notifications["gmail_enabled"] = _parse_bool(
        env.get("GMAIL_ENABLED"),
        notifications.get("gmail_enabled", False),
    )

    execution["paper_trading_enabled"] = _parse_bool(
        env.get("PAPER_TRADING_ENABLED"),
        execution.get("paper_trading_enabled", True),
    )
    execution["execution_cost_preset"] = env.get(
        "EXECUTION_COST_PRESET",
        execution.get("execution_cost_preset", "simple"),
    )
    execution["paper_fee_bps"] = float(
        env.get(
            "PAPER_FEE_BPS",
            execution.get("paper_fee_bps", 0.0),
        )
    )
    default_fee_pct = execution.get("fee_pct")
    if default_fee_pct is None:
        default_fee_pct = float(execution.get("paper_fee_bps", 0.0)) / 10_000
    execution["fee_pct"] = float(env.get("FEE_PCT", default_fee_pct))
    execution["spread_pct"] = float(env.get("SPREAD_PCT", execution.get("spread_pct", 0.0005)))
    execution["slippage_pct"] = float(env.get("SLIPPAGE_PCT", execution.get("slippage_pct", 0.0005)))
    execution["fee_pct"], execution["spread_pct"], execution["slippage_pct"] = resolve_execution_costs(
        preset=execution["execution_cost_preset"],
        fee_pct=float(execution["fee_pct"]),
        spread_pct=float(execution["spread_pct"]),
        slippage_pct=float(execution["slippage_pct"]),
    )
    execution["paper_state_path"] = env.get(
        "PAPER_STATE_PATH",
        execution.get("paper_state_path", "data_lake/state/paper_broker_state.json"),
    )
    execution["paper_trade_log_path"] = env.get(
        "PAPER_TRADE_LOG_PATH",
        execution.get("paper_trade_log_path", "data_lake/state/paper_trade_ledger.jsonl"),
    )
    execution["paper_cycle_log_path"] = env.get(
        "PAPER_CYCLE_LOG_PATH",
        execution.get("paper_cycle_log_path", "data_lake/state/paper_cycle_log.jsonl"),
    )
    execution["paper_snapshot_path"] = env.get(
        "PAPER_SNAPSHOT_PATH",
        execution.get("paper_snapshot_path", "data_lake/state/paper_portfolio_snapshot.json"),
    )
    execution["paper_decision_trace_path"] = env.get(
        "PAPER_DECISION_TRACE_PATH",
        execution.get("paper_decision_trace_path", "data_lake/state/paper_decision_trace.jsonl"),
    )

    merged = dict(base_config)
    merged["trading"] = trading
    merged["data"] = data
    merged["ingestion"] = ingestion
    merged["runtime"] = runtime
    merged["logging"] = logging
    merged["notifications"] = notifications
    merged["llm"] = llm
    merged["execution"] = execution
    return merged


def load_config() -> AppConfig:
    """Load application configuration from env, sheet, and local cache."""
    env = _load_env()
    cache_path = Path(env.get("CONFIG_CACHE_PATH", "config/config_cache.json"))
    cache_data = _load_local_cache(cache_path)

    sheet_loader = GoogleSheetConfigLoader.from_env(env)
    sheet_data = sheet_loader.load() if sheet_loader.enabled else {}

    merged = {}
    merged.update(cache_data)
    merged.update(sheet_data)
    merged = _apply_env_overrides(merged, env)
    merged["env"] = env
    merged["cache_path"] = str(cache_path)

    return AppConfig.from_mapping(merged)
