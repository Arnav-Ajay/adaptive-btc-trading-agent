"""Standalone runner for scheduled paper-trading decisions."""

from __future__ import annotations

import logging
import os
import socket
from datetime import UTC, datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config.settings import load_config
from app.main import run_cycle
from app.monitoring.logger import configure_logging
from app.scheduler.job_runner import seconds_until_next_interval_with_offset


def _instance_id() -> str:
    """Build a scheduler instance identifier for log correlation."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _job_event_listener(event: JobExecutionEvent) -> None:
    """Log scheduler job lifecycle events."""
    logger = logging.getLogger(__name__)
    instance_id = _instance_id()
    if event.code == EVENT_JOB_EXECUTED:
        logger.info(
            "Trading scheduler job executed successfully: instance=%s job_id=%s scheduled_run_time=%s",
            instance_id,
            event.job_id,
            event.scheduled_run_time,
        )
    elif event.code == EVENT_JOB_MISSED:
        logger.warning(
            "Trading scheduler job missed its run window: instance=%s job_id=%s scheduled_run_time=%s",
            instance_id,
            event.job_id,
            event.scheduled_run_time,
        )
    elif event.code == EVENT_JOB_ERROR:
        logger.error(
            "Trading scheduler job failed: instance=%s job_id=%s scheduled_run_time=%s exception=%s",
            instance_id,
            event.job_id,
            event.scheduled_run_time,
            event.exception,
        )


def run() -> None:
    """Run the configured trading scheduler."""
    config = load_config()
    configure_logging(config.logging.level, service_name="trading")
    logger = logging.getLogger(__name__)

    scheduler = BlockingScheduler(timezone="UTC")
    initial_delay = seconds_until_next_interval_with_offset(
        config.runtime.schedule_minutes,
        config.runtime.decision_offset_minutes,
    )
    first_run_at = datetime.now(UTC) + timedelta(seconds=initial_delay)
    instance_id = _instance_id()

    scheduler.add_job(
        run_cycle,
        trigger="interval",
        minutes=config.runtime.schedule_minutes,
        next_run_time=first_run_at,
        id="paper_trading_cycle",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        replace_existing=True,
    )
    scheduler.add_listener(_job_event_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    logger.info(
        (
            "Starting trading scheduler instance=%s cadence=%s offset_minutes=%s "
            "first_run=%s misfire_grace_time=%s"
        ),
        instance_id,
        config.runtime.schedule_minutes,
        config.runtime.decision_offset_minutes,
        first_run_at.isoformat(),
        120,
    )
    scheduler.start()


if __name__ == "__main__":
    run()
