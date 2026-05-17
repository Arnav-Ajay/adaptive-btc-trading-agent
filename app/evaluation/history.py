"""Persistence helpers for evaluation runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.evaluation.engine import EvaluationResult, serialize_evaluation_result


def _state_dir(data_lake_path: str) -> Path:
    return Path(data_lake_path) / "state" / "evaluations"


def latest_evaluation_path(data_lake_path: str) -> Path:
    """Return the path for the latest saved evaluation result."""
    return _state_dir(data_lake_path) / "evaluation_latest.json"


def evaluation_history_path(data_lake_path: str) -> Path:
    """Return the path for the append-only evaluation history log."""
    return _state_dir(data_lake_path) / "evaluation_history.jsonl"


def save_evaluation_result(data_lake_path: str, result: EvaluationResult) -> dict[str, Any]:
    """Persist the latest evaluation and append it to history."""
    payload = serialize_evaluation_result(result)
    state_dir = _state_dir(data_lake_path)
    state_dir.mkdir(parents=True, exist_ok=True)

    latest_path = latest_evaluation_path(data_lake_path)
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

    history_path = evaluation_history_path(data_lake_path)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return payload


def load_evaluation_history(data_lake_path: str, limit: int = 10) -> list[dict[str, Any]]:
    """Load recent persisted evaluation runs."""
    path = evaluation_history_path(data_lake_path)
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines[-limit:]]
