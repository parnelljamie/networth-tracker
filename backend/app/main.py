from __future__ import annotations

import logging
import logging.handlers
import shutil
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine

from alembic import command
from app import __version__
from app.api import (
    accounts,
    balances,
    goal,
    holdings,
    insights,
    instruments,
    loans,
    networth,
    people,
    projection,
    recurring,
)
from app.api import settings as settings_api
from app.api import sync as sync_api
from app.config import settings
from app.core import paths
from app.core.errors import register_error_handlers
from app.db import SessionLocal
from app.jobs import backup_job, register_jobs, startup_job
from app.schemas.health import HealthResponse
from app.services import seed_service, settings_service
from app.services.sync import control as sync_control
from app.services.sync import lan as sync_lan
from app.services.sync import outbox as sync_outbox

logger = logging.getLogger("app")


def _configure_logging(logs_dir: Path) -> None:
    handler = logging.handlers.RotatingFileHandler(
        logs_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(console)


def _backup_before_upgrade_if_needed(cfg: Config, db_file: Path) -> None:
    """Phase 9 task 2: if the database is behind head, copy it to backups/ before upgrading."""
    if not db_file.exists():
        return
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with engine.connect() as conn:
            current_rev = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()

    if current_rev == head_rev:
        return

    backups_dir = Path(settings.data_dir) / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backups_dir / f"networth-pre-upgrade-{__version__}.db"
    shutil.copy2(db_file, backup_path)
    logger.info("Backed up database to %s before migrating %s -> %s", backup_path, current_rev, head_rev)


def _alembic_upgrade_head() -> None:
    backend_dir = paths.resource_dir() / "backend"
    db_file = Path(settings.data_dir) / "networth.db"
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    _backup_before_upgrade_if_needed(cfg, db_file)
    command.upgrade(cfg, "head")


scheduler = BackgroundScheduler(timezone="Europe/London")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    data_dir = Path(settings.data_dir)
    (data_dir / "backups").mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    _configure_logging(data_dir / "logs")

    logger.info("Starting up, data_dir=%s, role=%s", data_dir, settings.role)
    _alembic_upgrade_head()

    with SessionLocal() as db:
        seed_service.ensure_defaults(db)
        price_refresh_minutes = settings_service.get(db, "price_refresh_minutes", 15)
        sync_control.start_if_enabled(db)

    register_jobs(scheduler, price_refresh_minutes, role=settings.role)
    scheduler.start()
    logger.info("Scheduler started")

    threading.Thread(target=startup_job, args=(settings.role,), daemon=True).start()

    yield

    scheduler.shutdown(wait=False)
    sync_lan.stop()
    # Back up on the way out too: the 22:30 job only runs if the app is open then. The phone
    # doesn't: the PC holds the master copy and its backups.
    if settings.role != "phone":
        backup_job()
    logger.info("Shut down")


app = FastAPI(title="Net Worth Tracker", version=__version__, lifespan=lifespan)
register_error_handlers(app)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, role=settings.role)


app.include_router(people.router)
app.include_router(accounts.router)
app.include_router(balances.router)
app.include_router(settings_api.router)
app.include_router(networth.router)
app.include_router(instruments.router)
app.include_router(holdings.router)
app.include_router(loans.router)
app.include_router(recurring.router)
app.include_router(projection.router)
app.include_router(goal.router)
app.include_router(insights.router)
if settings.role != "phone":
    # Imports are a PC job and pull in pandas, which the phone doesn't ship (docs/07-mobile.md).
    from app.api import imports as imports_api
    from app.api import trading212 as trading212_api

    app.include_router(imports_api.router)
    app.include_router(trading212_api.router)
app.include_router(sync_api.router)
sync_outbox.install(app)


_frontend_dist = paths.resource_dir() / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = _frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_frontend_dist / "index.html")
