"""Healthcheck for the combined ingestion + trading worker."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import load_config
from app.ingestion.state_store import StateStore
from app.monitoring.logger import configure_logging
from app.scheduler.healthcheck import is_state_fresh
from app.scheduler.trading_healthcheck import _latest_cycle_timestamp


logger = logging.getLogger(__name__)


def main() -> int:
    """Run the combined worker healthcheck."""
    config = load_config()
    configure_logging(config.logging.level, service_name="worker")

    ingestion_state = StateStore(config.ingestion.state_path).load()
    ingestion_ok = is_state_fresh(
        last_successful_run_at=ingestion_state.last_successful_run_at,
        max_staleness_minutes=config.ingestion.health_max_staleness_minutes,
        now=datetime.now(UTC),
    )

    latest_cycle_at = _latest_cycle_timestamp(Path(config.execution.paper_cycle_log_path))
    trading_ok = is_state_fresh(
        last_successful_run_at=latest_cycle_at,
        max_staleness_minutes=config.runtime.health_max_staleness_minutes,
        now=datetime.now(UTC),
    )

    if ingestion_ok and trading_ok:
        logger.info(
            "Worker healthcheck passed: ingestion_at=%s trading_at=%s",
            ingestion_state.last_successful_run_at,
            latest_cycle_at,
        )
        return 0

    logger.error(
        "Worker healthcheck failed: ingestion_at=%s trading_at=%s",
        ingestion_state.last_successful_run_at,
        latest_cycle_at,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
