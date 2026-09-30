"""docs/07-mobile.md "Sync client (phone)".

A sync: find the PC on the home network, send it the outbox, download a fresh copy of its
database and swap it in. Anything that fails before the swap leaves the phone exactly as it was,
and the PC ignores ops it has already applied, so the next sync simply tries again.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import now_utc
from app.core.errors import DomainError
from app.services.sync import ids, outbox, snapshot

logger = logging.getLogger(__name__)

HELLO_TIMEOUT_S = 2.0
TRANSFER_TIMEOUT_S = 120.0

HttpFactory = Callable[[str, str, float], httpx.Client]


@dataclass
class SyncConfig:
    hosts: list[str] = field(default_factory=list)
    port: int = 8766
    token: str = ""
    device_id: int | None = None
    pc_name: str = ""
    last_sync_at: str | None = None
    last_attempt_at: str | None = None
    last_report: dict[str, Any] | None = None

    @property
    def paired(self) -> bool:
        return bool(self.hosts and self.token)


def _config_path() -> Path:
    return Path(settings.data_dir) / "sync.json"


def load_config() -> SyncConfig:
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SyncConfig()
    known = {k: v for k, v in data.items() if k in SyncConfig.__dataclass_fields__}
    return SyncConfig(**known)


def save_config(cfg: SyncConfig) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    os.replace(tmp, path)


def forget() -> None:
    _config_path().unlink(missing_ok=True)


def parse_pairing_uri(uri: str) -> SyncConfig:
    parsed = urlparse(uri.strip())
    if parsed.scheme not in ("passbook", "waymark") or parsed.netloc != "pair":
        raise DomainError("validation", "That isn't a Waymark pairing link", field="pairing_uri")
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    try:
        hosts = [h for h in q["h"].split(",") if h]
        cfg = SyncConfig(hosts=hosts, port=int(q["p"]), token=q["t"], device_id=int(q["d"]), pc_name=q.get("n", "PC"))
    except (KeyError, ValueError) as exc:
        raise DomainError("validation", "The pairing link is incomplete", field="pairing_uri") from exc
    if not cfg.hosts or not cfg.token:
        raise DomainError("validation", "The pairing link is incomplete", field="pairing_uri")
    return cfg


def _default_http(base_url: str, token: str, timeout: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)


def _find_pc(cfg: SyncConfig, http: HttpFactory) -> tuple[str, dict[str, Any]] | None:
    for host in cfg.hosts:
        base = f"http://{host}:{cfg.port}"
        try:
            with http(base, cfg.token, HELLO_TIMEOUT_S) as client:
                r = client.get("/sync/v1/hello")
            if r.status_code == 200:
                return base, r.json()
            if r.status_code in (401, 429):
                raise DomainError("not_paired", "The PC doesn't recognise this phone any more. Pair it again.")
        except httpx.HTTPError:
            continue
    return None


def pair(uri: str, http: HttpFactory | None = None) -> SyncConfig:
    cfg = parse_pairing_uri(uri)
    found = _find_pc(cfg, http or _default_http)
    if found is None:
        raise DomainError(
            "pc_unreachable",
            "Couldn't reach the PC. Check the phone is on the same Wi-Fi and Waymark is open on the PC.",
        )
    cfg.pc_name = found[1].get("server_name") or cfg.pc_name
    save_config(cfg)
    return cfg


def _swap_database(incoming: Path, db_file: Path, dispose: Callable[[], None]) -> None:
    dispose()  # close every pooled connection to the old file
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
        os.replace(db_file, db_file.with_name(db_file.name + ".previous"))
    for suffix in ("-wal", "-shm"):
        db_file.with_name(db_file.name + suffix).unlink(missing_ok=True)
    os.replace(incoming, db_file)
    ids.reset_counter()


def sync_now(
    db: Session,
    *,
    http: HttpFactory | None = None,
    db_file: Path | None = None,
    dispose: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Run one sync and return its report. `db` is only used to read the outbox and the schema
    revision; it is closed before the database file is replaced."""
    from app import db as app_db

    http = http or _default_http
    db_file = db_file or snapshot.database_file(db)
    dispose = dispose or app_db.engine.dispose
    cfg = load_config()
    if not cfg.paired:
        raise DomainError("not_paired", "This phone isn't paired with a PC yet")

    incoming = db_file.with_name(db_file.name + ".incoming")
    lock = outbox.sync_lock()
    if not lock.acquire(blocking=False):
        return {"status": "already_running"}
    try:
        cfg.last_attempt_at = now_utc().isoformat()
        found = _find_pc(cfg, http)
        if found is None:
            save_config(cfg)
            return {"status": "pc_unreachable"}
        base, hello = found

        local_rev = snapshot.schema_revision(db)
        if hello.get("schema_revision") != local_rev:
            save_config(cfg)
            return {
                "status": "version_mismatch",
                "message": f"The PC runs Waymark {hello.get('app_version')}. "
                "Update the app on both so they match, then sync again.",
            }

        ops = outbox.list_ops(db)
        payload = {
            "ops": [
                {
                    "op_id": o.op_id,
                    "method": o.method,
                    "path": o.path,
                    "query": o.query,
                    "body": json.loads(o.body) if o.body else None,
                    "response": json.loads(o.response) if o.response else None,
                    "summary": o.summary,
                }
                for o in ops
            ]
        }
        db.rollback()
        db.close()

        with http(base, cfg.token, TRANSFER_TIMEOUT_S) as client:
            r = client.post("/sync/v1/push", json=payload)
            r.raise_for_status()
            results = r.json()["results"]
            with client.stream("GET", "/sync/v1/snapshot") as s:
                s.raise_for_status()
                with open(incoming, "wb") as f:
                    for chunk in s.iter_bytes():
                        f.write(chunk)

        if snapshot.schema_revision_of_file(incoming) != local_rev:
            incoming.unlink(missing_ok=True)
            raise DomainError("sync_failed", "The copy from the PC didn't look right; nothing was changed")

        _swap_database(incoming, db_file, dispose)

        rejected = [r for r in results if r["status"] != "applied"]
        report = {
            "status": "ok",
            "at": now_utc().isoformat(),
            "applied": len(results) - len(rejected),
            "rejected": [{"summary": r["summary"], "message": r["message"]} for r in rejected],
        }
        cfg.last_sync_at = report["at"]
        cfg.last_report = report
        save_config(cfg)
        logger.info("Sync with %s: %d applied, %d rejected", cfg.pc_name, report["applied"], len(rejected))
        return report
    except httpx.HTTPError as exc:
        logger.warning("Sync failed: %s", exc)
        incoming.unlink(missing_ok=True)
        save_config(cfg)
        return {"status": "failed", "message": "Lost the connection to the PC part-way; nothing was changed. Try again."}
    finally:
        lock.release()
