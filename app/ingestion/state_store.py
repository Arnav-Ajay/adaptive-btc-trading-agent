# app/ingestion/state_store.py
"""State persistence for ingestion jobs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class IngestionState:
    """Persisted state for ingestion runs."""

    last_successful_run_at: str | None = None
    last_ingested_timestamp: str | None = None
    rows_written: int = 0
    provider: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class StateStore:
    """Read and write ingestion state files."""

    def __init__(self, path: str) -> None:
        """Initialize the state store."""
        self.path = Path(path)

    def load(self) -> IngestionState:
        """Load persisted ingestion state if it exists."""
        if not self.path.exists():
            return IngestionState()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return IngestionState(**payload)

    def save(self, state: IngestionState) -> None:
        """Persist ingestion state atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_successful_run_at": state.last_successful_run_at,
            "last_ingested_timestamp": state.last_ingested_timestamp,
            "rows_written": state.rows_written,
            "provider": state.provider,
            "metadata": state.metadata,
        }
        temp_path = self.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        temp_path.replace(self.path)

    @staticmethod
    def utc_now_iso() -> str:
        """Return the current UTC time in ISO 8601 format."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
