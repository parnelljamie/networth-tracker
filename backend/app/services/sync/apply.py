"""docs/07-mobile.md "Applying a push (desktop)".

Each op the phone recorded is replayed against the PC's own API in-process, so the same routers,
services and validation run as if the change had been made on the PC. Ids the phone made are
swapped for the ids the PC made, and every op is recorded so a retried push changes nothing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.clock import now_utc_naive
from app.models.sync import SyncAppliedOp, SyncDevice
from app.services.sync.ids import learn_ids, rewrite_ids, rewrite_path

logger = logging.getLogger(__name__)


@dataclass
class Op:
    op_id: str
    method: str
    path: str
    query: str = ""
    body: Any = None
    response: Any = None
    summary: str = ""


@dataclass
class OpResult:
    op_id: str
    status: str  # applied | rejected
    message: str | None = None
    summary: str = ""
    id_map: dict[int, int] = field(default_factory=dict)


def _main_app() -> FastAPI:
    from app.main import app  # the PC's own API; imported late to avoid a cycle

    return app


def _dispatch(app: FastAPI, method: str, path: str, query: str, body: Any) -> tuple[int, Any]:
    async def call() -> tuple[int, Any]:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://waymark.local") as client:
            response = await client.request(
                method,
                path,
                params=query or None,
                json=body,
            )
            try:
                data = response.json() if response.content else None
            except ValueError:
                data = None
            return response.status_code, data

    return asyncio.run(call())


def _error_message(status: int, data: Any) -> str:
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list) and detail and isinstance(detail[0], dict):
            return str(detail[0].get("msg", "Invalid request"))
    if status == 404:
        return "Not found on the PC (it may have been deleted there)"
    return f"The PC answered {status}"


_LEDGER_SHORTFALL = re.compile(r"\bheld\b")


def _explain(path: str, message: str) -> str:
    """The ledger re-checks every sale in date order, so its message can name a different sale
    from the phone's. Say what happened in plain words and keep the detail."""
    if path.endswith("/transactions") and _LEDGER_SHORTFALL.search(message):
        return f"There weren't enough units left on the PC for this sale; they were sold there first. ({message})"
    return message


def _rewrite_query(query: str, id_map: dict[int, int]) -> tuple[str, int | None]:
    missing: int | None = None
    pairs = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if value.isdigit():
            new_value, gap = rewrite_ids(int(value), id_map)
            missing = missing or gap
            value = str(new_value)
        pairs.append((key, value))
    return urlencode(pairs), missing


def _load_map(raw: str) -> dict[int, int]:
    return {int(k): int(v) for k, v in json.loads(raw or "{}").items()}


def apply_ops(db: Session, device: SyncDevice, ops: list[Op], app: FastAPI | None = None) -> list[OpResult]:
    app = app or _main_app()
    id_map: dict[int, int] = {}
    results: list[OpResult] = []

    for op in ops:
        done = db.get(SyncAppliedOp, op.op_id)
        if done is not None:
            earlier = _load_map(done.id_map)
            id_map.update(earlier)
            results.append(OpResult(op.op_id, done.status, done.message, op.summary, earlier))
            continue

        path, missing = rewrite_path(op.path, id_map)
        query, missing_q = _rewrite_query(op.query, id_map)
        body, missing_b = rewrite_ids(op.body, id_map)
        missing = missing or missing_q or missing_b

        learned: dict[int, int] = {}
        if missing is not None:
            status, message = "rejected", "Depends on an earlier change that the PC rejected"
        else:
            # End any read transaction first: the dispatched request writes on its own connection.
            db.commit()
            try:
                code, data = _dispatch(app, op.method, path, query, body)
            except Exception as exc:  # never let one op stop the rest
                logger.exception("Sync op %s %s failed", op.method, path)
                code, data = 500, {"detail": str(exc)}
            if 200 <= code < 300:
                status, message = "applied", None
                learn_ids(op.response, data, learned)
            else:
                status, message = "rejected", _explain(path, _error_message(code, data))

        db.add(
            SyncAppliedOp(
                op_id=op.op_id,
                device_id=device.id,
                applied_at=now_utc_naive(),
                status=status,
                message=message,
                id_map=json.dumps({str(k): v for k, v in learned.items()}),
            )
        )
        db.commit()
        id_map.update(learned)
        results.append(OpResult(op.op_id, status, message, op.summary, learned))

    return results
