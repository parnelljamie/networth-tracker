"""docs/01-architecture.md "Scheduled jobs": SQLite online backup, keep newest `backup_keep`."""
from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import today
from app.core.errors import DomainError
from app.services import settings_service

logger = logging.getLogger(__name__)


def backups_dir() -> Path:
    d = Path(settings.data_dir) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _db_path() -> Path:
    from app.db import db_path

    return db_path()


def validate_copy_dir(raw: object) -> str:
    """The optional second backup folder: "" turns it off; otherwise an absolute folder path that
    can be created and written to (checked now, so a typo is caught in Settings, not at 22:30)."""
    value = str(raw or "").strip().strip('"')
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        raise DomainError("validation", "Use a full folder path, e.g. C:\\Users\\you\\OneDrive\\Waymark backups", field="backup_copy_dir")
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".waymark-write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        raise DomainError("validation", f"Can't write to that folder: {exc.strerror or exc}", field="backup_copy_dir") from exc
    return str(path)


@dataclass
class BackupResult:
    path: Path
    copied_to: Path | None = None
    copy_error: str | None = None


def run_backup(db: Session) -> Path:
    return run_backup_with_copy(db).path


def run_backup_with_copy(db: Session) -> BackupResult:
    """Local backup, then a copy into `backup_copy_dir` if one is set. The local backup always
    stands; a failed copy (e.g. the drive is offline) is logged and reported, not raised."""
    path = _run_local_backup(db)
    result = BackupResult(path=path)
    copy_dir = str(settings_service.get(db, "backup_copy_dir", "") or "").strip()
    if copy_dir:
        try:
            target_dir = Path(copy_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            # Copying the finished backup file (not the live database) is safe.
            result.copied_to = Path(shutil.copy2(path, target_dir / path.name))
            _prune_old_backups(target_dir, settings_service.get(db, "backup_keep", 30))
        except OSError as exc:
            result.copy_error = f"Couldn't copy the backup to {copy_dir}: {exc.strerror or exc}"
            logger.warning(result.copy_error)
    return result


def _run_local_backup(db: Session) -> Path:
    """SQLite online backup API — safe to run while the app is writing."""
    directory = backups_dir()
    filename = f"networth-{today().isoformat()}.db"
    dest = directory / filename

    source_conn = sqlite3.connect(_db_path())
    try:
        dest_conn = sqlite3.connect(dest)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    keep = settings_service.get(db, "backup_keep", 30)
    _prune_old_backups(directory, keep)
    return dest


def _prune_old_backups(directory: Path, keep: int) -> None:
    files = sorted(directory.glob("networth-*.db"), key=lambda p: p.name, reverse=True)
    for stale in files[keep:]:
        stale.unlink(missing_ok=True)


@dataclass
class BackupInfo:
    filename: str
    size_bytes: int
    created_at: str


def list_backups() -> list[BackupInfo]:
    directory = backups_dir()
    files = sorted(directory.glob("networth-*.db"), key=lambda p: p.name, reverse=True)
    return [
        BackupInfo(
            filename=f.name,
            size_bytes=f.stat().st_size,
            created_at=datetime.fromtimestamp(f.stat().st_mtime, tz=UTC).isoformat(),
        )
        for f in files
    ]
