"""
signal-engine/scheduler.py
Scheduled jobs — daily session resets and news cache updates.
Uses APScheduler with AsyncIO backend.
"""
from __future__ import annotations
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog
import pytz

from db.redis_client import reset_risk_state, reset_session
from config import ATLAS_MODE

log = structlog.get_logger(__name__)
EST = pytz.timezone("America/New_York")

scheduler = AsyncIOScheduler(timezone=EST)


def start_scheduler() -> None:
    """Register all scheduled jobs and start the scheduler."""

    # Reset daily risk state at 20:00 EST (start of Asia session / new trading day)
    # Rule 7.3: Daily loss limit resets each calendar day
    scheduler.add_job(
        _reset_daily_state,
        CronTrigger(hour=20, minute=0, timezone=EST),
        id="daily_reset",
        replace_existing=True,
    )

    # Reset session state at 20:00 EST for new Asia range
    scheduler.add_job(
        _reset_session_state,
        CronTrigger(hour=20, minute=0, timezone=EST),
        id="session_reset",
        replace_existing=True,
    )

    scheduler.start()
    log.info("scheduler_started", jobs=len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    log.info("scheduler_stopped")


async def _reset_daily_state() -> None:
    """
    Resets daily risk counters at 20:00 EST.
    Implements Rule 7.3: daily loss limit resets per trading day.
    """
    await reset_risk_state()
    log.info("daily_risk_state_reset",
             time=datetime.now(EST).isoformat())


async def _reset_session_state() -> None:
    """Clears the session Redis key so the new Asia range is fresh."""
    await reset_session()
    log.info("session_state_reset",
             time=datetime.now(EST).isoformat())