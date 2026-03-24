# app/scheduler/healthcheck.py
"""Healthcheck for the market data ingestion service."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

from app.config.settings import load_config
from app.ingestion.state_store import StateStore
from app.monitoring.logger import configure_logging


logger = logging.getLogger(__name__)


def is_state_fresh(
    last_successful_run_at: str | None,
    max_staleness_minutes: int,
    now: datetime | None = None,
) -> bool:
    """Return whether the ingestion heartbeat is within the freshness threshold."""
    if not last_successful_run_at:
        return False

    heartbeat = datetime.fromisoformat(last_successful_run_at)
    current = now or datetime.now(UTC)
    delta_minutes = (current - heartbeat).total_seconds() / 60
    return delta_minutes <= max_staleness_minutes


def main() -> int:
    """Run the ingestion healthcheck."""
    config = load_config()
    configure_logging(config.logging.level, service_name="ingestion")
    state = StateStore(config.ingestion.state_path).load()
    if is_state_fresh(
        last_successful_run_at=state.last_successful_run_at,
        max_staleness_minutes=config.ingestion.health_max_staleness_minutes,
    ):
        logger.info(
            "Ingestion healthcheck passed: last_successful_run_at=%s threshold_minutes=%s",
            state.last_successful_run_at,
            config.ingestion.health_max_staleness_minutes,
        )
        return 0

    logger.error(
        "Ingestion healthcheck failed: last_successful_run_at=%s threshold_minutes=%s",
        state.last_successful_run_at,
        config.ingestion.health_max_staleness_minutes,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
