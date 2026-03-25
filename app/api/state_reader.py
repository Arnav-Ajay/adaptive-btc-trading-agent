"""Read current runtime state for the UI/API layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.backtest.history import latest_backtest_path, load_backtest_history
from app.config.schema import AppConfig
from app.data.parquet_market_data import ParquetMarketDataClient


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


def _load_jsonl_records(path: Path, limit: int) -> list[dict[str, Any]]:
    """Load the latest JSONL records if the file exists."""
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return []
    return [json.loads(line) for line in lines[-limit:]]


def load_dashboard_state(
    config: AppConfig,
    include_candles: bool = True,
    candle_intervals: list[str] | None = None,
    candle_limit: int | None = None,
) -> dict[str, Any]:
    """Load the latest ingestion and trading artifacts for the dashboard."""
    ingestion_state = _load_json(Path(config.ingestion.state_path))
    ingestion_gap_audit = _load_json(Path(config.data.data_lake_path) / "state" / "ingestion_gap_audit.json")
    broker_state = _load_json(Path(config.execution.paper_state_path))
    portfolio_snapshot = _load_json(Path(config.execution.paper_snapshot_path))
    latest_cycle = _load_latest_jsonl(Path(config.execution.paper_cycle_log_path))
    latest_trace = _load_latest_jsonl(Path(config.execution.paper_decision_trace_path))
    latest_trade = _load_latest_jsonl(Path(config.execution.paper_trade_log_path))
    latest_backtest = _load_json(latest_backtest_path(config.data.data_lake_path))
    recent_trades = _load_jsonl_records(Path(config.execution.paper_trade_log_path), limit=25)
    recent_cycles = _load_jsonl_records(Path(config.execution.paper_cycle_log_path), limit=50)
    recent_backtests = load_backtest_history(config.data.data_lake_path, limit=10)
    recent_candles: list[dict[str, Any]] = []
    chart_candles: dict[str, list[dict[str, Any]]] = {}
    if include_candles:
        client = ParquetMarketDataClient(config=config)
        intervals = candle_intervals or ["1m", "10m", "30m", "1d"]

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
            chart_candles[interval] = serialize(client.fetch_dashboard_candles(interval=interval, limit=candle_limit))
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
        "recent_trades": recent_trades,
        "recent_cycles": recent_cycles,
        "recent_backtests": recent_backtests,
        "recent_candles": recent_candles,
        "chart_candles": chart_candles,
    }
