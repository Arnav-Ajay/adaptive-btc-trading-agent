# app/config/settings.py
"""Configuration loading helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config.schema import AppConfig
from app.config.sheet_loader import GoogleSheetConfigLoader


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
