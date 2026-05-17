"""Standalone runner for the combined ingestion -> trading worker."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import UTC, datetime, timedelta

from app.config.settings import load_config
from app.ingestion.collector import CoinbaseIngestionService
from app.main import run_cycle
from app.monitoring.logger import configure_logging
from app.scheduler.collector_runner import (
    _find_recent_gap_start,
    _has_bootstrap_data,
)
from app.scheduler.job_runner import seconds_until_next_interval


def _instance_id() -> str:
    """Build a worker instance identifier for log correlation."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _safe_worker_cycle(service: CoinbaseIngestionService, config, run_lock: threading.Lock) -> None:
    """Run one ingestion cycle followed by one trading cycle without overlaps."""
    logger = logging.getLogger(__name__)
    if not run_lock.acquire(blocking=False):
        logger.warning("Skipping worker cycle because another ingestion/trading cycle is already in progress")
        return
    try:
        service.collect_once()
        run_cycle(config=load_config())
    finally:
        run_lock.release()


def _maybe_run_startup_catch_up(
    *,
    config,
    service: CoinbaseIngestionService,
    run_lock: threading.Lock,
) -> bool:
    """Run one immediate worker cycle on startup if state/data indicates catch-up is needed."""
    logger = logging.getLogger(__name__)
    state = service.state_store.load()

    if not state.last_successful_run_at and not _has_bootstrap_data(config):
        logger.warning(
            "Running initial bootstrap worker cycle because no ingestion state or canonical market data exists yet"
        )
        _safe_worker_cycle(service, config, run_lock)
        return True

    if state.last_successful_run_at:
        try:
            last_success = datetime.fromisoformat(state.last_successful_run_at).astimezone(UTC)
        except ValueError:
            logger.warning("Unable to parse last_successful_run_at for worker catch-up check: %s", state.last_successful_run_at)
        else:
            minutes_since_success = (datetime.now(UTC) - last_success).total_seconds() / 60
            if minutes_since_success > (config.ingestion.schedule_minutes + 5):
                logger.warning(
                    "Running startup worker catch-up because last successful ingestion is stale: %.1fm",
                    minutes_since_success,
                )
                _safe_worker_cycle(service, config, run_lock)
                return True

    gap_start = _find_recent_gap_start(config)
    if gap_start is not None:
        logger.warning(
            "Running startup worker catch-up because recent parquet history has an internal gap starting at %s",
            gap_start.isoformat(),
        )
        _safe_worker_cycle(service, config, run_lock)
        return True

    return False


def _next_boundary(interval_minutes: int, now: datetime | None = None) -> datetime:
    """Return the next aligned UTC boundary for the worker cadence."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    aligned_minute = (current.minute // interval_minutes) * interval_minutes
    boundary = current.replace(minute=aligned_minute, second=0, microsecond=0)
    if boundary <= current:
        boundary += timedelta(minutes=interval_minutes)
    return boundary


def run() -> None:
    """Run the configured combined market execution worker."""
    config = load_config()
    configure_logging(config.logging.level, service_name="worker")
    logger = logging.getLogger(__name__)

    if not config.ingestion.enabled:
        logger.info("Combined worker is disabled because ingestion is disabled by configuration")
        return

    service = CoinbaseIngestionService(config=config)
    run_lock = threading.Lock()
    instance_id = _instance_id()
    first_run_at = _next_boundary(config.ingestion.schedule_minutes)

    logger.info(
        (
            "Starting combined worker instance=%s provider=%s symbol=%s "
            "interval=%s cadence=%s first_run=%s scheduler=exact_boundary_loop"
        ),
        instance_id,
        config.ingestion.provider,
        config.trading.symbol,
        config.ingestion.interval,
        config.ingestion.schedule_minutes,
        first_run_at.isoformat(),
    )

    _maybe_run_startup_catch_up(config=config, service=service, run_lock=run_lock)

    while True:
        target_run_at = _next_boundary(config.ingestion.schedule_minutes)
        sleep_seconds = seconds_until_next_interval(config.ingestion.schedule_minutes)
        time.sleep(max(sleep_seconds, 0.0))

        woke_at = datetime.now(UTC)
        drift_seconds = max((woke_at - target_run_at).total_seconds(), 0.0)
        if drift_seconds > 5:
            logger.warning(
                "Worker woke late for scheduled boundary: instance=%s scheduled_run_time=%s woke_at=%s drift_seconds=%.3f",
                instance_id,
                target_run_at.isoformat(),
                woke_at.isoformat(),
                drift_seconds,
            )
        else:
            logger.info(
                "Worker woke on schedule: instance=%s scheduled_run_time=%s woke_at=%s drift_seconds=%.3f",
                instance_id,
                target_run_at.isoformat(),
                woke_at.isoformat(),
                drift_seconds,
            )

        try:
            _safe_worker_cycle(service, config, run_lock)
            logger.info(
                "Worker cycle executed successfully: instance=%s scheduled_run_time=%s",
                instance_id,
                target_run_at.isoformat(),
            )
        except Exception:
            logger.exception(
                "Worker cycle failed: instance=%s scheduled_run_time=%s",
                instance_id,
                target_run_at.isoformat(),
            )


if __name__ == "__main__":
    run()
