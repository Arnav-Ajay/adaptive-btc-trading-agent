"""Persistence helpers for saved backtest runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.backtest.engine import BacktestResult


def _state_dir(data_lake_path: str) -> Path:
    return Path(data_lake_path) / "state" / "backtesting"


def latest_backtest_path(data_lake_path: str) -> Path:
    """Return the path for the latest saved backtest result."""
    return _state_dir(data_lake_path) / "backtest_latest.json"


def backtest_history_path(data_lake_path: str) -> Path:
    """Return the path for the append-only backtest history log."""
    return _state_dir(data_lake_path) / "backtest_history.jsonl"


def serialize_backtest_result(result: BacktestResult) -> dict[str, Any]:
    """Convert a backtest result into a JSON-serializable payload."""
    return {
        "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "symbol": result.symbol,
        "strategy_profile": result.strategy_profile,
        "interval": result.interval,
        "decision_cadence_minutes": result.decision_cadence_minutes,
        "start_at": result.start_at,
        "end_at": result.end_at,
        "candles_processed": result.candles_processed,
        "metrics": asdict(result.metrics),
        "final_snapshot": asdict(result.final_snapshot),
        "trades": result.trades,
        "steps": [asdict(step) for step in result.steps],
        "equity_curve": result.equity_curve,
        "benchmark_curve": result.benchmark_curve,
        "drawdowns": result.drawdowns,
        "halted_reason": result.halted_reason,
        "halted_at": result.halted_at,
    }


def save_backtest_result(data_lake_path: str, result: BacktestResult) -> dict[str, Any]:
    """Persist the latest backtest and append it to history."""
    payload = serialize_backtest_result(result)
    state_dir = _state_dir(data_lake_path)
    state_dir.mkdir(parents=True, exist_ok=True)

    latest_path = latest_backtest_path(data_lake_path)
    temp_path = latest_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        temp_path.replace(latest_path)
    except PermissionError:
        try:
            latest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_path.unlink(missing_ok=True)
        except PermissionError:
            temp_path.unlink(missing_ok=True)

    history_path = backtest_history_path(data_lake_path)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return payload


def load_backtest_history(data_lake_path: str, limit: int = 10) -> list[dict[str, Any]]:
    """Load recent persisted backtest runs."""
    path = backtest_history_path(data_lake_path)
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines[-limit:]]
