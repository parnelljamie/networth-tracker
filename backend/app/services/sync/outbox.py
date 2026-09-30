"""docs/07-mobile.md "Outbox (phone)".

On the phone, every successful change made through `/api/` is recorded so the PC can replay it.
While a sync is running, changes are refused with 423 so nothing is written into a database that
is about to be replaced.
"""
from __future__ import annotations

import inspect
import json
import logging
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.clock import now_utc_naive
from app.db import get_db
from app.models.sync import SyncOutbox
from app.services.sync import ids  # noqa: F401  (registers phone id allocation)
from app.services.sync.describe import describe

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Local-only or meaningless on the PC. Prefix match on the path.
OUTBOX_EXCLUDE = (
    "/api/prices/refresh",
    "/api/sync",
    "/api/backup",
    "/api/system/",
    "/api/imports",
    "/api/trading212",
    "/api/snapshots/rebuild",
    # Read-only calculations that happen to be POSTs.
    "/api/projection/compare",
)
_EXCLUDE_SUFFIXES = ("/schedule/simulate",)

_sync_lock = threading.Lock()


def sync_lock() -> threading.Lock:
    """Held by the sync client for the whole of a sync."""
    return _sync_lock


def is_recorded(method: str, path: str) -> bool:
    if method not in MUTATING_METHODS or not path.startswith("/api/"):
        return False
    return not (path.startswith(OUTBOX_EXCLUDE) or path.endswith(_EXCLUDE_SUFFIXES))


def pending_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(SyncOutbox)) or 0


def list_ops(db: Session) -> list[SyncOutbox]:
    return list(db.scalars(select(SyncOutbox).order_by(SyncOutbox.id)))


@contextmanager
def _session(app: FastAPI) -> Iterator[Session]:
    # Resolve get_db the way FastAPI would, honouring overrides so tests use their own database.
    # It may be a generator dependency (the real one) or return a session directly.
    provided = app.dependency_overrides.get(get_db, get_db)()
    if inspect.isgenerator(provided):
        try:
            yield next(provided)
        finally:
            provided.close()
    else:
        yield provided


def _describe(app: FastAPI, method: str, path: str, body: Any) -> str:
    try:
        with _session(app) as db:
            return describe(db, method, path, body)
    except Exception:
        logger.exception("Could not describe %s %s", method, path)
        return f"{method} {path}"


def _record(
    app: FastAPI, method: str, path: str, query: str, body: Any, response: Any, summary: str
) -> None:
    with _session(app) as db:
        db.add(
            SyncOutbox(
                op_id=str(uuid.uuid4()),
                created_at=now_utc_naive(),
                method=method,
                path=path,
                query=query,
                body=None if body is None else json.dumps(body),
                response=None if response is None else json.dumps(response),
                summary=summary,
            )
        )
        db.commit()


def install(app: FastAPI) -> None:
    """Add the outbox middleware. It does nothing unless `settings.role == "phone"`."""

    @app.middleware("http")
    async def _outbox_middleware(request: Request, call_next):  # noqa: ANN001, ANN202
        method, path = request.method, request.url.path
        if settings.role != "phone" or not is_recorded(method, path):
            return await call_next(request)

        if _sync_lock.locked():
            return JSONResponse(
                status_code=423,
                content={
                    "error": {
                        "code": "sync_in_progress",
                        "message": "Syncing with your PC. Try again in a moment.",
                        "field": None,
                    }
                },
            )

        raw = await request.body()
        content_type = request.headers.get("content-type", "")
        if raw and "application/json" not in content_type:
            # Uploads and forms aren't replayable on the PC; let them through unrecorded.
            return await call_next(request)
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            return await call_next(request)

        # Before the change runs, so a deleted account still has its name.
        summary = await run_in_threadpool(_describe, app, method, path, body)
        response = await call_next(request)
        if not 200 <= response.status_code < 300:
            return response

        chunks = [chunk async for chunk in response.body_iterator]
        payload = b"".join(chunks)
        try:
            response_json = json.loads(payload) if payload else None
        except ValueError:
            response_json = None
        try:
            await run_in_threadpool(
                _record, app, method, path, request.url.query, body, response_json, summary
            )
        except Exception:
            logger.exception("Could not record %s %s in the sync outbox", method, path)

        return Response(
            content=payload,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
