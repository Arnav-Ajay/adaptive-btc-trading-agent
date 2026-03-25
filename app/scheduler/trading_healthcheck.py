"""Healthcheck for the scheduled trading service."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import load_config
from app.monitoring.logger import configure_logging
from app.scheduler.healthcheck import is_state_fresh


logger = logging.getLogger(__name__)


def _latest_cycle_timestamp(path: Path) -> str | None:
    """Load the latest recorded_at value from the cycle log."""
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    record = json.loads(lines[-1])
    return record.get("recorded_at")


def main() -> int:
    """Run the trading healthcheck."""
    config = load_config()
    configure_logging(config.logging.level, service_name="trading")
    cycle_log_path = Path(config.execution.paper_cycle_log_path)
    latest_recorded_at = _latest_cycle_timestamp(cycle_log_path)
    if is_state_fresh(
        last_successful_run_at=latest_recorded_at,
        max_staleness_minutes=config.runtime.health_max_staleness_minutes,
        now=datetime.now(UTC),
    ):
        logger.info(
            "Trading healthcheck passed: latest_cycle_at=%s threshold_minutes=%s",
            latest_recorded_at,
            config.runtime.health_max_staleness_minutes,
        )
        return 0

    logger.error(
        "Trading healthcheck failed: latest_cycle_at=%s threshold_minutes=%s",
        latest_recorded_at,
        config.runtime.health_max_staleness_minutes,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
