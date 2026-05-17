"""Read current runtime state for the UI/API layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.backtest.history import latest_backtest_path, load_backtest_history
from app.config.schema import AppConfig
from app.data.parquet_market_data import ParquetMarketDataClient
from app.evaluation.history import latest_evaluation_path, load_evaluation_history
from app.simulation.history import latest_simulation_path, load_simulation_history


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file if it exists."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_latest_jsonl(path: Path) -> dict[str, Any] | None:
    """Load the last non-empty JSONL record if the file exists."""
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def _load_jsonl_records(path: Path, limit: int | None) -> list[dict[str, Any]]:
    """Load the latest JSONL records if the file exists."""
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return []
    if limit is None:
        return [json.loads(line) for line in lines]
    return [json.loads(line) for line in lines[-limit:]]


def _fallback_ingestion_state_from_parquet(config: AppConfig) -> dict[str, Any] | None:
    """Synthesize a minimal ingestion heartbeat from canonical parquet when the state file is missing."""
    try:
        bounds = ParquetMarketDataClient(config=config).fetch_candle_bounds(interval=config.ingestion.interval)
    except (FileNotFoundError, ValueError, OSError):
        return None
    if bounds.latest is None:
        return None
    latest_timestamp = bounds.latest.replace(microsecond=0).isoformat()
    payload: dict[str, Any] = {
        "provider": config.ingestion.provider,
        "interval": config.ingestion.interval,
        "status": "parquet_fallback",
        "last_ingested_timestamp": latest_timestamp,
        "last_successful_run_at": latest_timestamp,
    }
    if bounds.earliest is not None:
        payload["first_ingested_timestamp"] = bounds.earliest.replace(microsecond=0).isoformat()
    return payload


def load_dashboard_state(
    config: AppConfig,
    include_candles: bool = True,
    candle_intervals: list[str] | None = None,
    candle_limit: int | None = None,
    candle_limits_by_interval: dict[str, int | None] | None = None,
    include_ingestion: bool = True,
    include_paper: bool = True,
    include_backtests: bool = True,
    include_simulations: bool = True,
    include_evaluations: bool = True,
) -> dict[str, Any]:
    """Load the latest ingestion and trading artifacts for the dashboard."""
    ingestion_state = _load_json(Path(config.ingestion.state_path)) if include_ingestion else None
    if include_ingestion and ingestion_state is None:
        ingestion_state = _fallback_ingestion_state_from_parquet(config)
    ingestion_gap_audit = (
        _load_json(Path(config.data.data_lake_path) / "state" / "ingestion" / "ingestion_gap_audit.json")
        if include_ingestion
        else None
    )
    broker_state = _load_json(Path(config.execution.paper_state_path)) if include_paper else None
    portfolio_snapshot = _load_json(Path(config.execution.paper_snapshot_path)) if include_paper else None
    latest_cycle = _load_latest_jsonl(Path(config.execution.paper_cycle_log_path)) if include_paper else None
    latest_trace = _load_latest_jsonl(Path(config.execution.paper_decision_trace_path)) if include_paper else None
    latest_trade = _load_latest_jsonl(Path(config.execution.paper_trade_log_path)) if include_paper else None
    latest_backtest = _load_json(latest_backtest_path(config.data.data_lake_path)) if include_backtests else None
    latest_simulation = _load_json(latest_simulation_path(config.data.data_lake_path)) if include_simulations else None
    latest_evaluation = _load_json(latest_evaluation_path(config.data.data_lake_path)) if include_evaluations else None
    recent_trades = _load_jsonl_records(Path(config.execution.paper_trade_log_path), limit=25) if include_paper else []
    recent_cycles = _load_jsonl_records(Path(config.execution.paper_cycle_log_path), limit=None) if include_paper else []
    recent_backtests = load_backtest_history(config.data.data_lake_path, limit=10) if include_backtests else []
    recent_simulations = load_simulation_history(config.data.data_lake_path, limit=10) if include_simulations else []
    recent_evaluations = load_evaluation_history(config.data.data_lake_path, limit=10) if include_evaluations else []
    recent_candles: list[dict[str, Any]] = []
    chart_candles: dict[str, list[dict[str, Any]]] = {}
    llm_state = {
        "enabled": bool(config.llm.enabled),
        "used_in_last_cycle": False,
        "status": "unknown",
        "summary": "",
        "decision": None,
        "decision_present": False,
        "decision_valid": False,
    }
    if latest_cycle is not None:
        llm_review = latest_cycle.get("llm_review") or {}
        if isinstance(llm_review, dict):
            llm_state = {
                "enabled": bool(llm_review.get("enabled", config.llm.enabled)),
                "used_in_last_cycle": bool(llm_review.get("used", False)),
                "status": str(llm_review.get("status", "unknown")),
                "summary": str(llm_review.get("summary", "")),
                "decision": llm_review.get("decision"),
                "decision_present": bool(llm_review.get("decision_present", False)),
                "decision_valid": bool(llm_review.get("decision_valid", False)),
            }
    if include_candles:
        client = ParquetMarketDataClient(config=config)
        intervals = candle_intervals or ["1m", "10m", "30m", "1d", "1month"]

        def serialize(candles):
            return [
                {
                    "timestamp": candle.timestamp.replace(microsecond=0).isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in candles
            ]
        for interval in intervals:
            if candle_limits_by_interval is not None and interval in candle_limits_by_interval:
                interval_limit = candle_limits_by_interval[interval]
                if interval_limit is None:
                    candles = client.store.load_candles(
                        symbol=config.trading.symbol,
                        interval=interval,
                        limit=None,
                    )
                else:
                    candles = client.fetch_dashboard_candles(interval=interval, limit=interval_limit)
            else:
                candles = client.fetch_dashboard_candles(interval=interval, limit=candle_limit)
            chart_candles[interval] = serialize(candles)
        recent_candles = chart_candles.get("1m", [])

    return {
        "ingestion_state": ingestion_state,
        "ingestion_gap_audit": ingestion_gap_audit,
        "broker_state": broker_state,
        "portfolio_snapshot": portfolio_snapshot,
        "latest_cycle": latest_cycle,
        "latest_trace": latest_trace,
        "latest_trade": latest_trade,
        "latest_backtest": latest_backtest,
        "latest_simulation": latest_simulation,
        "latest_evaluation": latest_evaluation,
        "recent_trades": recent_trades,
        "recent_cycles": recent_cycles,
        "recent_backtests": recent_backtests,
        "recent_simulations": recent_simulations,
        "recent_evaluations": recent_evaluations,
        "recent_candles": recent_candles,
        "chart_candles": chart_candles,
        "llm_state": llm_state,
    }
