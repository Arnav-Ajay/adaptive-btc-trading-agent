# app/scheduler/collector_runner.py
"""Standalone runner for scheduled market data ingestion."""

from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import UTC, datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config.settings import load_config
from app.ingestion.collector import CoinbaseIngestionService
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.ingestion.state_store import StateStore
from app.monitoring.logger import configure_logging
from app.scheduler.job_runner import seconds_until_next_interval


def _instance_id() -> str:
    """Build a scheduler instance identifier for log correlation."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _job_event_listener(event: JobExecutionEvent) -> None:
    """Log scheduler job lifecycle events."""
    logger = logging.getLogger(__name__)
    instance_id = _instance_id()
    if event.code == EVENT_JOB_EXECUTED:
        logger.info(
            "Scheduler job executed successfully: instance=%s job_id=%s scheduled_run_time=%s",
            instance_id,
            event.job_id,
            event.scheduled_run_time,
        )
    elif event.code == EVENT_JOB_MISSED:
        logger.warning(
            "Scheduler job missed its run window: instance=%s job_id=%s scheduled_run_time=%s",
            instance_id,
            event.job_id,
            event.scheduled_run_time,
        )
    elif event.code == EVENT_JOB_ERROR:
        logger.error(
            "Scheduler job failed: instance=%s job_id=%s scheduled_run_time=%s exception=%s",
            instance_id,
            event.job_id,
            event.scheduled_run_time,
            event.exception,
        )


def _safe_collect_once(service: CoinbaseIngestionService, run_lock: threading.Lock) -> None:
    """Run one ingestion cycle while preventing overlapping catch-up executions."""
    logger = logging.getLogger(__name__)
    if not run_lock.acquire(blocking=False):
        logger.warning("Skipping ingestion run because another collection is already in progress")
        return
    try:
        service.collect_once()
    finally:
        run_lock.release()


def _schedule_catch_up(
    scheduler: BlockingScheduler,
    service: CoinbaseIngestionService,
    run_lock: threading.Lock,
) -> None:
    """Queue an immediate one-shot catch-up run."""
    scheduler.add_job(
        _safe_collect_once,
        trigger="date",
        run_date=datetime.now(UTC) + timedelta(seconds=1),
        args=[service, run_lock],
        id="coinbase_ingestion_catchup",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )


def _maybe_catch_up_from_state(
    scheduler: BlockingScheduler,
    config,
    service: CoinbaseIngestionService,
    run_lock: threading.Lock,
) -> None:
    """Queue a catch-up run if persisted ingestion state is already stale at startup."""
    logger = logging.getLogger(__name__)
    state = StateStore(config.ingestion.state_path).load()
    if not state.last_successful_run_at:
        return
    try:
        last_success = datetime.fromisoformat(state.last_successful_run_at).astimezone(UTC)
    except ValueError:
        logger.warning("Unable to parse last_successful_run_at for catch-up check: %s", state.last_successful_run_at)
        return
    minutes_since_success = (datetime.now(UTC) - last_success).total_seconds() / 60
    if minutes_since_success > (config.ingestion.schedule_minutes + 5):
        logger.warning(
            "Scheduling startup catch-up ingestion because last successful run is stale: %.1fm",
            minutes_since_success,
        )
        _schedule_catch_up(scheduler=scheduler, service=service, run_lock=run_lock)


def _find_recent_gap_start(config) -> datetime | None:
    """Return the earliest recent missing candle timestamp if an internal gap exists."""
    if config.ingestion.interval != "1m":
        return None

    store = ParquetMarketDataStore(config.data.data_lake_path)
    lookback_candles = max((config.ingestion.schedule_minutes * 12), 360)
    candles = store.load_candles(
        symbol=config.trading.symbol,
        interval=config.ingestion.interval,
        limit=lookback_candles,
    )
    if len(candles) < 2:
        return None

    expected_step = timedelta(minutes=1)
    for previous, current in zip(candles, candles[1:]):
        previous_ts = previous.timestamp.astimezone(UTC)
        current_ts = current.timestamp.astimezone(UTC)
        gap = current_ts - previous_ts
        if gap > expected_step:
            return previous_ts + expected_step
    return None


def _maybe_catch_up_from_recent_gaps(
    scheduler: BlockingScheduler,
    config,
    service: CoinbaseIngestionService,
    run_lock: threading.Lock,
) -> None:
    """Queue a catch-up run if recent parquet history contains missing 1m candles."""
    logger = logging.getLogger(__name__)
    gap_start = _find_recent_gap_start(config)
    if gap_start is None:
        return
    logger.warning(
        "Scheduling startup catch-up ingestion because recent parquet history has an internal gap starting at %s",
        gap_start.isoformat(),
    )
    _schedule_catch_up(scheduler=scheduler, service=service, run_lock=run_lock)


def run() -> None:
    """Run the configured ingestion scheduler."""
    config = load_config()
    configure_logging(config.logging.level, service_name="ingestion")
    logger = logging.getLogger(__name__)

    if not config.ingestion.enabled:
        logger.info("Ingestion service is disabled by configuration")
        return

    service = CoinbaseIngestionService(config=config)
    scheduler = BlockingScheduler(timezone="UTC")
    run_lock = threading.Lock()
    initial_delay = seconds_until_next_interval(config.ingestion.schedule_minutes)
    first_run_at = datetime.now(UTC) + timedelta(seconds=initial_delay)
    instance_id = _instance_id()

    scheduler.add_job(
        _safe_collect_once,
        trigger="interval",
        minutes=config.ingestion.schedule_minutes,
        next_run_time=first_run_at,
        args=[service, run_lock],
        id="coinbase_ingestion",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
        replace_existing=True,
    )
    def listener(event: JobExecutionEvent) -> None:
        _job_event_listener(event)
        if event.code == EVENT_JOB_MISSED and event.job_id == "coinbase_ingestion":
            logging.getLogger(__name__).warning(
                "Queueing immediate catch-up ingestion after missed scheduler boundary: scheduled_run_time=%s",
                event.scheduled_run_time,
            )
            _schedule_catch_up(scheduler=scheduler, service=service, run_lock=run_lock)

    scheduler.add_listener(listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)
    _maybe_catch_up_from_state(
        scheduler=scheduler,
        config=config,
        service=service,
        run_lock=run_lock,
    )
    _maybe_catch_up_from_recent_gaps(
        scheduler=scheduler,
        config=config,
        service=service,
        run_lock=run_lock,
    )

    logger.info(
        (
            "Starting ingestion scheduler instance=%s provider=%s symbol=%s "
            "interval=%s cadence=%s first_run=%s misfire_grace_time=%s"
        ),
        instance_id,
        config.ingestion.provider,
        config.trading.symbol,
        config.ingestion.interval,
        config.ingestion.schedule_minutes,
        first_run_at.isoformat(),
        60,
    )
    scheduler.start()


if __name__ == "__main__":
    run()
