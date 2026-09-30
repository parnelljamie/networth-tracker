"""A consistent copy of the database for the phone, and the schema revision both sides compare."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from sqlalchemy.orm import Session


def schema_revision(db: Session) -> str | None:
    return MigrationContext.configure(db.connection()).get_current_revision()


def database_file(db: Session) -> Path:
    path = db.get_bind().url.database
    if not path or path == ":memory:":
        raise RuntimeError("The database isn't a file")
    return Path(path)


def schema_revision_of_file(path: Path) -> str | None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()
    return row[0] if row else None


def make_copy(db: Session) -> Path:
    """SQLite online backup into a temp file: safe while the app keeps writing. The caller
    deletes the file."""
    fd, name = tempfile.mkstemp(prefix="waymark-sync-", suffix=".db")
    os.close(fd)
    dest = Path(name)
    source = sqlite3.connect(database_file(db))
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
            # The phone has no use for the PC's pairing records; keep token hashes on the PC.
            target.execute("DELETE FROM sync_applied_ops")
            target.execute("DELETE FROM sync_devices")
            target.execute("DELETE FROM sync_outbox")
            target.commit()
        finally:
            target.close()
    finally:
        source.close()
    return dest
