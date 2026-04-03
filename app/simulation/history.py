"""Persistence helpers for saved simulation sweeps."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.backtest.history import serialize_backtest_result
from app.simulation.engine import SimulationCandidate, SimulationResult


def _state_dir(data_lake_path: str) -> Path:
    return Path(data_lake_path) / "state" / "simulations"


def latest_simulation_path(data_lake_path: str) -> Path:
    return _state_dir(data_lake_path) / "simulation_latest.json"


def simulation_history_path(data_lake_path: str) -> Path:
    return _state_dir(data_lake_path) / "simulation_history.jsonl"


def _serialize_candidate(candidate: SimulationCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "params": candidate.params,
        "summary": {
            "metrics": {
                "total_return_percent": candidate.result.metrics.total_return_percent,
                "buy_and_hold_return_percent": candidate.result.metrics.buy_and_hold_return_percent,
                "max_drawdown_percent": candidate.result.metrics.max_drawdown_percent,
                "sharpe_ratio": candidate.result.metrics.sharpe_ratio,
                "filled_trade_count": candidate.result.metrics.filled_trade_count,
                "profit_factor": candidate.result.metrics.profit_factor,
                "win_rate_percent": candidate.result.metrics.win_rate_percent,
            },
            "final_equity_usd": candidate.result.final_snapshot.equity_usd,
            "halted_reason": candidate.result.halted_reason,
            "halted_at": candidate.result.halted_at,
        },
        "backtest": serialize_backtest_result(candidate.result),
    }


def serialize_simulation_result(result: SimulationResult) -> dict[str, Any]:
    recorded_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    candidates = [_serialize_candidate(candidate) for candidate in result.candidates]
    return {
        "recorded_at": recorded_at,
        "symbol": result.symbol,
        "interval": result.interval,
        "start_at": result.start_at,
        "end_at": result.end_at,
        "candidate_count": result.candidate_count,
        "best_candidate_id": result.best_candidate_id,
        "parameter_grid": result.parameter_grid,
        "candidates": candidates,
    }


def save_simulation_result(data_lake_path: str, result: SimulationResult) -> dict[str, Any]:
    payload = serialize_simulation_result(result)
    state_dir = _state_dir(data_lake_path)
    state_dir.mkdir(parents=True, exist_ok=True)

    latest_path = latest_simulation_path(data_lake_path)
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

    history_path = simulation_history_path(data_lake_path)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return payload


def load_simulation_history(data_lake_path: str, limit: int = 10) -> list[dict[str, Any]]:
    path = simulation_history_path(data_lake_path)
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines[-limit:]]
