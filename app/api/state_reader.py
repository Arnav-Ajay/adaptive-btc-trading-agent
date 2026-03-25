"""Read current runtime state for the UI/API layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.schema import AppConfig
from app.data.parquet_market_data import ParquetMarketDataClient


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file if it exists."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def load_dashboard_state(config: AppConfig) -> dict[str, Any]:
    """Load the latest ingestion and trading artifacts for the dashboard."""
    ingestion_state = _load_json(Path(config.ingestion.state_path))
    broker_state = _load_json(Path(config.execution.paper_state_path))
    portfolio_snapshot = _load_json(Path(config.execution.paper_snapshot_path))
    latest_cycle = _load_latest_jsonl(Path(config.execution.paper_cycle_log_path))
    latest_trace = _load_latest_jsonl(Path(config.execution.paper_decision_trace_path))
    latest_trade = _load_latest_jsonl(Path(config.execution.paper_trade_log_path))
    recent_trades = _load_jsonl_records(Path(config.execution.paper_trade_log_path), limit=25)
    recent_cycles = _load_jsonl_records(Path(config.execution.paper_cycle_log_path), limit=50)
    client = ParquetMarketDataClient(config=config)

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

    recent_candles = serialize(client.fetch_dashboard_candles(interval="1m"))
    chart_candles = {
        "1m": recent_candles,
        "10m": serialize(client.fetch_dashboard_candles(interval="10m")),
        "30m": serialize(client.fetch_dashboard_candles(interval="30m")),
        "1d": serialize(client.fetch_dashboard_candles(interval="1d")),
    }

    return {
        "ingestion_state": ingestion_state,
        "broker_state": broker_state,
        "portfolio_snapshot": portfolio_snapshot,
        "latest_cycle": latest_cycle,
        "latest_trace": latest_trace,
        "latest_trade": latest_trade,
        "recent_trades": recent_trades,
        "recent_cycles": recent_cycles,
        "recent_candles": recent_candles,
        "chart_candles": chart_candles,
    }
