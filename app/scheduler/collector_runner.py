# app/scheduler/collector_runner.py
"""Standalone runner for scheduled market data ingestion."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config.settings import load_config
from app.ingestion.collector import CoinbaseIngestionService
from app.monitoring.logger import configure_logging
from app.scheduler.job_runner import seconds_until_next_interval


def _job_event_listener(event: JobExecutionEvent) -> None:
    """Log scheduler job lifecycle events."""
    logger = logging.getLogger(__name__)
    if event.code == EVENT_JOB_EXECUTED:
        logger.info(
            "Scheduler job executed successfully: job_id=%s scheduled_run_time=%s",
            event.job_id,
            event.scheduled_run_time,
        )
    elif event.code == EVENT_JOB_MISSED:
        logger.warning(
            "Scheduler job missed its run window: job_id=%s scheduled_run_time=%s",
            event.job_id,
            event.scheduled_run_time,
        )
    elif event.code == EVENT_JOB_ERROR:
        logger.error(
            "Scheduler job failed: job_id=%s scheduled_run_time=%s exception=%s",
            event.job_id,
            event.scheduled_run_time,
            event.exception,
        )


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
    initial_delay = seconds_until_next_interval(config.ingestion.schedule_minutes)
    first_run_at = datetime.now(UTC) + timedelta(seconds=initial_delay)

    scheduler.add_job(
        service.collect_once,
        trigger="interval",
        minutes=config.ingestion.schedule_minutes,
        next_run_time=first_run_at,
        id="coinbase_ingestion",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_listener(_job_event_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    logger.info(
        "Starting ingestion scheduler provider=%s symbol=%s interval=%s cadence=%s first_run=%s",
        config.ingestion.provider,
        config.trading.symbol,
        config.ingestion.interval,
        config.ingestion.schedule_minutes,
        first_run_at.isoformat(),
    )
    scheduler.start()


if __name__ == "__main__":
    run()
