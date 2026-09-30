"""docs/07-mobile.md "Sync server (desktop)".

A second, separate FastAPI app that serves only `/sync/v1/*`, run by its own uvicorn server on
`0.0.0.0:sync_port`. The main app keeps binding 127.0.0.1, so nothing else is reachable from the
network. Every request needs a paired phone's bearer token.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import __version__
from app.core.clock import now_utc_naive
from app.db import get_db
from app.models.sync import SyncDevice
from app.services.sync import apply as apply_service
from app.services.sync import devices, snapshot

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8766
MAX_FAILURES = 5
FAILURE_WINDOW_S = 60
LOCKOUT_S = 600

_failures: dict[str, deque[float]] = defaultdict(deque)
_locked_until: dict[str, float] = {}
_failures_lock = threading.Lock()


def _note_failure(ip: str) -> None:
    now = time.monotonic()
    with _failures_lock:
        q = _failures[ip]
        q.append(now)
        while q and now - q[0] > FAILURE_WINDOW_S:
            q.popleft()
        if len(q) >= MAX_FAILURES:
            _locked_until[ip] = now + LOCKOUT_S
            q.clear()


def _is_locked(ip: str) -> bool:
    with _failures_lock:
        until = _locked_until.get(ip)
        if until is None:
            return False
        if time.monotonic() >= until:
            del _locked_until[ip]
            return False
        return True


def reset_rate_limit() -> None:
    with _failures_lock:
        _failures.clear()
        _locked_until.clear()


def paired_device(request: Request, db: Session = Depends(get_db)) -> SyncDevice:
    ip = request.client.host if request.client else "?"
    if _is_locked(ip):
        raise HTTPException(status_code=429, detail="Too many failed attempts; try again later")
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    device = devices.authenticate(db, token)
    if device is None:
        _note_failure(ip)
        logger.warning("Sync request from %s refused: bad or missing token", ip)
        raise HTTPException(status_code=401, detail="Not paired")
    return device


class HelloOut(BaseModel):
    app_version: str
    schema_revision: str | None
    server_name: str
    device_id: int


class OpIn(BaseModel):
    op_id: str
    method: str
    path: str
    query: str = ""
    body: object = None
    response: object = None
    summary: str = ""


class PushIn(BaseModel):
    ops: list[OpIn]


class OpResultOut(BaseModel):
    op_id: str
    status: str
    message: str | None = None
    summary: str = ""


class PushOut(BaseModel):
    results: list[OpResultOut]


lan_app = FastAPI(title="Waymark sync", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)


@lan_app.get("/sync/v1/hello", response_model=HelloOut)
def hello(device: SyncDevice = Depends(paired_device), db: Session = Depends(get_db)) -> HelloOut:
    return HelloOut(
        app_version=__version__,
        schema_revision=snapshot.schema_revision(db),
        server_name=devices.pc_name(),
        device_id=device.id,
    )


@lan_app.post("/sync/v1/push", response_model=PushOut)
def push(payload: PushIn, device: SyncDevice = Depends(paired_device), db: Session = Depends(get_db)) -> PushOut:
    ops = [apply_service.Op(**op.model_dump()) for op in payload.ops]
    results = apply_service.apply_ops(db, device, ops)
    device = db.get(SyncDevice, device.id) or device
    device.last_sync_at = now_utc_naive()
    db.commit()
    applied = sum(r.status == "applied" for r in results)
    logger.info("Sync push from %s: %d applied, %d rejected", device.name, applied, len(results) - applied)
    return PushOut(
        results=[OpResultOut(op_id=r.op_id, status=r.status, message=r.message, summary=r.summary) for r in results]
    )


@lan_app.get("/sync/v1/snapshot")
def get_snapshot(device: SyncDevice = Depends(paired_device), db: Session = Depends(get_db)) -> FileResponse:
    path = snapshot.make_copy(db)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename="networth.db",
        headers={"X-Schema-Revision": snapshot.schema_revision(db) or ""},
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


class _Server:
    def __init__(self) -> None:
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None
        self.port: int | None = None
        self.lock = threading.Lock()


_state = _Server()


def is_running() -> bool:
    return _state.server is not None and _state.thread is not None and _state.thread.is_alive()


def start(port: int = DEFAULT_PORT) -> None:
    with _state.lock:
        if is_running() and _state.port == port:
            return
        _stop_locked()
        config = uvicorn.Config(lan_app, host="0.0.0.0", port=port, log_config=None, access_log=False)
        server = uvicorn.Server(config)
        # Off the main thread uvicorn leaves signal handling to the main server.
        thread = threading.Thread(target=server.run, name="waymark-sync-lan", daemon=True)
        thread.start()
        _state.server, _state.thread, _state.port = server, thread, port
        logger.info("Phone sync listening on 0.0.0.0:%d", port)


def _stop_locked() -> None:
    if _state.server is not None:
        _state.server.should_exit = True
        if _state.thread is not None:
            _state.thread.join(timeout=5)
        logger.info("Phone sync stopped")
    _state.server, _state.thread, _state.port = None, None, None


def stop() -> None:
    with _state.lock:
        _stop_locked()
