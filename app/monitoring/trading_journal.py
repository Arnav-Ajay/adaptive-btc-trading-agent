"""Persistent trading-cycle journal outputs."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.config.schema import AppConfig
from app.utils.models import OrderResult, PortfolioSnapshot


class TradingJournal:
    """Write append-only cycle logs and the latest portfolio snapshot."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize output paths for trading state artifacts."""
        self.cycle_log_path = Path(config.execution.paper_cycle_log_path)
        self.snapshot_path = Path(config.execution.paper_snapshot_path)
        self.decision_trace_path = Path(config.execution.paper_decision_trace_path)

    def next_cycle_number(self) -> int:
        """Return the next sequential cycle number for journal records."""
        if not self.cycle_log_path.exists():
            return 1
        lines = [line for line in self.cycle_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return 1
        latest_record = json.loads(lines[-1])
        return int(latest_record.get("cycle", 0)) + 1

    def record_cycle(
        self,
        cycle: int,
        regime: str,
        strategy_name: str,
        indicator_snapshot: dict[str, float | int | str],
        decision_trace: list[str],
        signal_count: int,
        execution_results: list[OrderResult],
        snapshot: PortfolioSnapshot,
        summary: str,
    ) -> None:
        """Persist one structured cycle record and refresh the latest snapshot."""
        record = {
            "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "cycle": cycle,
            "regime": regime,
            "strategy_name": strategy_name,
            "indicator_snapshot": indicator_snapshot,
            "decision_trace": decision_trace,
            "signal_count": signal_count,
            "execution_results": [
                {
                    "accepted": result.accepted,
                    "order_id": result.order_id,
                    "reason": result.reason,
                }
                for result in execution_results
            ],
            "summary": summary,
            "snapshot": asdict(snapshot),
        }

        self.cycle_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cycle_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

        trace_record = {
            "recorded_at": record["recorded_at"],
            "cycle": cycle,
            "regime": regime,
            "strategy_name": strategy_name,
            "indicator_snapshot": indicator_snapshot,
            "decision_trace": decision_trace,
        }
        self.decision_trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.decision_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace_record) + "\n")

        latest_snapshot = {
            "recorded_at": record["recorded_at"],
            "cycle": cycle,
            "regime": regime,
            "strategy_name": strategy_name,
            "summary": summary,
            "snapshot": asdict(snapshot),
        }
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.snapshot_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(latest_snapshot, handle, indent=2)
        temp_path.replace(self.snapshot_path)
