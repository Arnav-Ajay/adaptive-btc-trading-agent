# app/config/settings.py
"""Configuration loading helpers."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config.schema import AppConfig
from app.config.sheet_loader import GoogleSheetConfigLoader
from app.execution.cost_model import resolve_execution_costs


logger = logging.getLogger(__name__)


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


def _load_runtime_overrides(path: Path) -> dict[str, Any]:
    """Load runtime overrides written by the dashboard."""
    return _load_local_cache(path)


def _append_runtime_audit(path: Path, payload: dict[str, Any]) -> None:
    """Append a runtime settings change record for traceability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


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
    trading["dca_drop_percent"] = float(env.get("DCA_DROP_PERCENT", trading.get("dca_drop_percent", 1.5)))
    trading["dca_order_size_usd"] = float(
        env.get("DCA_ORDER_SIZE_USD", trading.get("dca_order_size_usd", 100.0))
    )
    trading["dca_enabled_in_bearish"] = _parse_bool(
        env.get("DCA_ENABLED_IN_BEARISH"),
        trading.get("dca_enabled_in_bearish", False),
    )
    trading["dca_weakening_bull_size_multiplier"] = float(
        env.get(
            "DCA_WEAKENING_BULL_SIZE_MULTIPLIER",
            trading.get("dca_weakening_bull_size_multiplier", 0.5),
        )
    )
    trading["max_btc_allocation_percent"] = float(
        env.get("MAX_BTC_ALLOCATION_PERCENT", trading.get("max_btc_allocation_percent", 70.0))
    )
    trading["weakening_bull_target_allocation_percent"] = float(
        env.get(
            "WEAKENING_BULL_TARGET_ALLOCATION_PERCENT",
            trading.get("weakening_bull_target_allocation_percent", 35.0),
        )
    )
    trading["bearish_target_allocation_percent"] = float(
        env.get(
            "BEARISH_TARGET_ALLOCATION_PERCENT",
            trading.get("bearish_target_allocation_percent", 15.0),
        )
    )
    trading["rebalance_tolerance_percent"] = float(
        env.get("REBALANCE_TOLERANCE_PERCENT", trading.get("rebalance_tolerance_percent", 2.5))
    )
    trading["rebalance_max_sell_fraction"] = float(
        env.get("REBALANCE_MAX_SELL_FRACTION", trading.get("rebalance_max_sell_fraction", 0.5))
    )
    trading["swing_enabled_in_weakening_bull"] = _parse_bool(
        env.get("SWING_ENABLED_IN_WEAKENING_BULL"),
        trading.get("swing_enabled_in_weakening_bull", False),
    )
    trading["swing_enabled_in_sideways"] = _parse_bool(
        env.get("SWING_ENABLED_IN_SIDEWAYS"),
        trading.get("swing_enabled_in_sideways", True),
    )
    trading["swing_enabled_in_bearish"] = _parse_bool(
        env.get("SWING_ENABLED_IN_BEARISH"),
        trading.get("swing_enabled_in_bearish", False),
    )
    trading["atr_multiplier"] = float(env.get("ATR_MULTIPLIER", trading.get("atr_multiplier", 2.0)))
    trading["swing_entry_rsi_max"] = float(
        env.get("SWING_ENTRY_RSI_MAX", trading.get("swing_entry_rsi_max", 40.0))
    )
    trading["swing_take_profit_percent"] = float(
        env.get("SWING_TAKE_PROFIT_PERCENT", trading.get("swing_take_profit_percent", 2.0))
    )
    trading["swing_no_follow_through_candles"] = int(
        env.get(
            "SWING_NO_FOLLOW_THROUGH_CANDLES",
            trading.get("swing_no_follow_through_candles", 3),
        )
    )
    trading["swing_follow_through_buffer_percent"] = float(
        env.get(
            "SWING_FOLLOW_THROUGH_BUFFER_PERCENT",
            trading.get("swing_follow_through_buffer_percent", 0.2),
        )
    )
    trading["pullback_entry_rsi_min"] = float(
        env.get("PULLBACK_ENTRY_RSI_MIN", trading.get("pullback_entry_rsi_min", 40.0))
    )
    trading["pullback_entry_rsi_max"] = float(
        env.get("PULLBACK_ENTRY_RSI_MAX", trading.get("pullback_entry_rsi_max", 62.0))
    )
    trading["pullback_min_retracement"] = float(
        env.get("PULLBACK_MIN_RETRACEMENT", trading.get("pullback_min_retracement", 0.30))
    )
    trading["pullback_max_retracement"] = float(
        env.get("PULLBACK_MAX_RETRACEMENT", trading.get("pullback_max_retracement", 0.75))
    )
    trading["pullback_stop_atr_multiplier"] = float(
        env.get("PULLBACK_STOP_ATR_MULTIPLIER", trading.get("pullback_stop_atr_multiplier", 0.75))
    )
    trading["pullback_take_profit_r"] = float(
        env.get("PULLBACK_TAKE_PROFIT_R", trading.get("pullback_take_profit_r", 2.0))
    )
    trading["pullback_no_follow_through_candles"] = int(
        env.get(
            "PULLBACK_NO_FOLLOW_THROUGH_CANDLES",
            trading.get("pullback_no_follow_through_candles", 3),
        )
    )
    trading["pullback_follow_through_buffer_percent"] = float(
        env.get(
            "PULLBACK_FOLLOW_THROUGH_BUFFER_PERCENT",
            trading.get("pullback_follow_through_buffer_percent", 0.2),
        )
    )
    trading["hybrid_dca_enabled_in_bullish"] = _parse_bool(
        env.get("HYBRID_DCA_ENABLED_IN_BULLISH"),
        trading.get("hybrid_dca_enabled_in_bullish", True),
    )
    trading["hybrid_dca_enabled_in_sideways"] = _parse_bool(
        env.get("HYBRID_DCA_ENABLED_IN_SIDEWAYS"),
        trading.get("hybrid_dca_enabled_in_sideways", False),
    )
    trading["hybrid_dca_enabled_in_weakening_bull"] = _parse_bool(
        env.get("HYBRID_DCA_ENABLED_IN_WEAKENING_BULL"),
        trading.get("hybrid_dca_enabled_in_weakening_bull", False),
    )
    trading["hybrid_dca_enabled_in_bearish"] = _parse_bool(
        env.get("HYBRID_DCA_ENABLED_IN_BEARISH"),
        trading.get("hybrid_dca_enabled_in_bearish", False),
    )
    trading["hybrid_dca_suppressed_by_pullback_signal"] = _parse_bool(
        env.get("HYBRID_DCA_SUPPRESSED_BY_PULLBACK_SIGNAL"),
        trading.get("hybrid_dca_suppressed_by_pullback_signal", True),
    )
    trading["hybrid_dca_suppressed_with_open_pullback_position"] = _parse_bool(
        env.get("HYBRID_DCA_SUPPRESSED_WITH_OPEN_PULLBACK_POSITION"),
        trading.get("hybrid_dca_suppressed_with_open_pullback_position", True),
    )
    trading["hybrid_bullish_dca_max_allocation_percent"] = float(
        env.get(
            "HYBRID_BULLISH_DCA_MAX_ALLOCATION_PERCENT",
            trading.get("hybrid_bullish_dca_max_allocation_percent", 20.0),
        )
    )
    trading["max_drawdown_percent"] = float(
        env.get("MAX_DRAWDOWN_PERCENT", trading.get("max_drawdown_percent", 25.0))
    )

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
        ingestion.get("state_path", "data_lake/state/ingestion/coinbase_btc_usd_1m.json"),
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
    runtime["decision_cadence_minutes"] = int(
        env.get("RUNTIME_DECISION_CADENCE_MINUTES", runtime.get("decision_cadence_minutes", 30))
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
    llm["api_base_url"] = env.get("OPENAI_API_BASE_URL", llm.get("api_base_url", "https://api.openai.com/v1/responses"))
    llm["timeout_seconds"] = int(env.get("OPENAI_TIMEOUT_SECONDS", llm.get("timeout_seconds", 20)))
    llm["allow_blocking"] = _parse_bool(
        env.get("LLM_ALLOW_BLOCKING"),
        llm.get("allow_blocking", True),
    )
    llm["min_size_multiplier"] = float(
        env.get("LLM_MIN_SIZE_MULTIPLIER", llm.get("min_size_multiplier", 0.5))
    )
    llm["max_signals_per_review"] = int(
        env.get("LLM_MAX_SIGNALS_PER_REVIEW", llm.get("max_signals_per_review", 8))
    )

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
        execution.get("paper_state_path", "data_lake/state/paper_trade/paper_broker_state.json"),
    )
    execution["paper_trade_log_path"] = env.get(
        "PAPER_TRADE_LOG_PATH",
        execution.get("paper_trade_log_path", "data_lake/state/paper_trade/paper_trade_ledger.jsonl"),
    )
    execution["paper_cycle_log_path"] = env.get(
        "PAPER_CYCLE_LOG_PATH",
        execution.get("paper_cycle_log_path", "data_lake/state/paper_trade/paper_cycle_log.jsonl"),
    )
    execution["paper_snapshot_path"] = env.get(
        "PAPER_SNAPSHOT_PATH",
        execution.get("paper_snapshot_path", "data_lake/state/paper_trade/paper_portfolio_snapshot.json"),
    )
    execution["paper_decision_trace_path"] = env.get(
        "PAPER_DECISION_TRACE_PATH",
        execution.get("paper_decision_trace_path", "data_lake/state/paper_trade/paper_decision_trace.jsonl"),
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


def _apply_runtime_overrides(base_config: dict[str, Any], runtime_overrides: dict[str, Any]) -> dict[str, Any]:
    """Overlay dashboard-managed runtime settings onto the merged config."""
    if not runtime_overrides:
        return base_config

    merged = dict(base_config)
    for section_name, section_value in runtime_overrides.items():
        if not isinstance(section_value, dict):
            continue
        current_section = dict(merged.get(section_name, {}))
        current_section.update(section_value)
        merged[section_name] = current_section
    return merged


def load_config() -> AppConfig:
    """Load application configuration with precedence: runtime override > env > sheet > cache > defaults."""
    env = _load_env()
    cache_path = Path(env.get("CONFIG_CACHE_PATH", "config/config_cache.json"))
    runtime_overrides_path = Path(env.get("RUNTIME_SETTINGS_PATH", "config/runtime_settings.json"))
    cache_data = _load_local_cache(cache_path)
    runtime_overrides = _load_runtime_overrides(runtime_overrides_path)

    sheet_loader = GoogleSheetConfigLoader.from_env(env)
    sheet_data = sheet_loader.load() if sheet_loader.enabled else {}

    merged = {}
    merged.update(cache_data)
    merged.update(sheet_data)
    merged = _apply_env_overrides(merged, env)
    merged = _apply_runtime_overrides(merged, runtime_overrides)
    merged["env"] = env
    merged["cache_path"] = str(cache_path)
    merged["runtime_overrides_path"] = str(runtime_overrides_path)

    return AppConfig.from_mapping(merged)
