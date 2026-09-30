"""docs/01-architecture.md "Scheduled jobs". Every job: own DB session, logs and never raises."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.clock import today
from app.db import SessionLocal
from app.providers.factory import default_provider
from app.services import backup_service, price_service, recurring_service, snapshot_service

logger = logging.getLogger("app.jobs")

_provider = default_provider()


def refresh_prices_job() -> None:
    try:
        with SessionLocal() as db:
            result = snapshot_service.refresh_quotes(db, _provider)
            logger.info(
                "refresh_prices: status=%s refreshed=%d failed=%d",
                result.status,
                result.refreshed,
                len(result.failed),
            )
    except Exception:
        logger.exception("refresh_prices job failed")


def daily_snapshot_job() -> None:
    try:
        with SessionLocal() as db:
            price_service.refresh_quotes(db, _provider, force=True)
            snapshot_service.take(db, today())
            logger.info("daily_snapshot: wrote snapshots for %s", today())
    except Exception:
        logger.exception("daily_snapshot job failed")


def record_due_plans_job() -> None:
    try:
        with SessionLocal() as db:
            touched = recurring_service.record_due(db, today())
            logger.info("record_due: processed %d plan(s)", len(touched))
    except Exception:
        logger.exception("record_due job failed")


def trading212_sync_job() -> None:
    try:
        from app.services import trading212_service  # PC only: pulls in the pandas importers

        with SessionLocal() as db:
            count = trading212_service.sync_all(db, _provider)
            logger.info("trading212_sync: synced %d account(s)", count)
    except Exception:
        logger.exception("trading212_sync job failed")


def backup_job() -> None:
    try:
        with SessionLocal() as db:
            result = backup_service.run_backup_with_copy(db)
            logger.info("backup: wrote %s (copy: %s)", result.path, result.copied_to or result.copy_error or "off")
    except Exception:
        logger.exception("backup job failed")


def catch_up_job() -> None:
    try:
        with SessionLocal() as db:
            snapshot_service.catch_up(db, _provider)
            logger.info("catch_up: complete")
    except Exception:
        logger.exception("catch_up job failed")


def startup_job(role: str = "desktop") -> None:
    """Runs once at startup. The 07:00 record_due trigger only fires if the app happens to be
    open then, so due plans are recorded here too, before catch_up snapshots today. Each job
    catches and logs its own failures, so one failing never stops the other."""
    # The phone doesn't record plans: the PC does, and the phone gets them at the next sync.
    if role != "phone":
        record_due_plans_job()
    catch_up_job()
    if role != "phone":
        try:
            from app.services import trading212_service

            with SessionLocal() as db:
                trading212_service.reset_interrupted(db)
        except Exception:
            logger.exception("trading212 reset failed")
        trading212_sync_job()


def register_jobs(scheduler: BackgroundScheduler, price_refresh_minutes: int = 15, role: str = "desktop") -> None:
    """docs/07-mobile.md "Roles": the phone keeps only price refresh and the daily snapshot;
    recording plans and backups belong to the PC, which holds the master copy."""
    scheduler.add_job(
        refresh_prices_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="8-21",
            minute=f"*/{max(1, price_refresh_minutes)}",
            timezone="Europe/London",
        ),
        id="refresh_prices",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    scheduler.add_job(
        daily_snapshot_job,
        trigger=CronTrigger(hour=22, minute=15, timezone="Europe/London"),
        id="daily_snapshot",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    if role == "phone":
        return
    scheduler.add_job(
        backup_job,
        trigger=CronTrigger(hour=22, minute=30, timezone="Europe/London"),
        id="backup",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    # Trading 212's history endpoints are rate limited per account, so once a day is plenty;
    # the Sync now button covers anything sooner.
    scheduler.add_job(
        trading212_sync_job,
        trigger=CronTrigger(hour=6, minute=30, timezone="Europe/London"),
        id="trading212_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    scheduler.add_job(
        record_due_plans_job,
        trigger=CronTrigger(hour=7, minute=0, timezone="Europe/London"),
        id="record_due_plans",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        replace_existing=True,
    )
