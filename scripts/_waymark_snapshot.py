"""Snapshot helper shared by scripts/save-my-data.ps1 and scripts/restore-my-data.ps1.

Kept in Python because the two things that must be done *correctly* here are both
sqlite3 concerns that PowerShell cannot do safely:

  * `backup`  - uses the sqlite3 **online backup API** (the same one
    `backend/app/services/backup_service.py::run_backup` uses). It takes a consistent
    copy of a database that another process is actively writing to. A plain file copy
    of a live WAL-mode database is NOT safe and can produce a torn/unreadable file.
  * `counts` / `dump` - read a database generically via `sqlite_master`, so a schema
    that gains tables later is captured without editing this file (same spirit as
    `export_service.export_all`, which iterates `Base.metadata.sorted_tables`).

Only the standard library is used, so this runs under any Python 3.8+ on PATH and does
not need the backend's uv environment.

Usage (all paths absolute):
    python _waymark_snapshot.py backup <source.db> <dest.db>
    python _waymark_snapshot.py counts <db>                 -> JSON {table: rowcount}
    python _waymark_snapshot.py dump   <db> <out.json>      -> full JSON row dump
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _connect_ro(db: Path) -> sqlite3.Connection:
    """Read-only connect, so we never create a -wal beside someone else's live database."""
    return sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)


def cmd_backup(source: Path, dest: Path) -> int:
    if not source.exists():
        print(f"ERROR: source database not found: {source}", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A leftover destination (or its sidecars) would otherwise be merged into, not replaced.
    for p in (dest, Path(str(dest) + "-wal"), Path(str(dest) + "-shm")):
        if p.exists():
            p.unlink()

    try:
        src_conn = sqlite3.connect(source)
        try:
            dst_conn = sqlite3.connect(dest)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
    except sqlite3.DatabaseError as exc:
        # Callers treat this as "not a usable SQLite database" and decide what to do; a raw
        # traceback here would only be noise on an expected path.
        print(f"ERROR: cannot read {source} as a SQLite database: {exc}", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        return 3

    # The copy inherits WAL journal mode; collapse it to a single self-contained file so
    # the snapshot is one artifact with no sidecars to lose or leave stale.
    conn = sqlite3.connect(dest)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.commit()
    finally:
        conn.close()
    for p in (Path(str(dest) + "-wal"), Path(str(dest) + "-shm")):
        if p.exists():
            p.unlink()
    return 0


def cmd_counts(db: Path) -> int:
    conn = _connect_ro(db)
    try:
        out = {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in _tables(conn)}
    finally:
        conn.close()
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_dump(db: Path, out_path: Path) -> int:
    conn = _connect_ro(db)
    conn.row_factory = sqlite3.Row
    try:
        data = {
            t: [dict(r) for r in conn.execute(f'SELECT * FROM "{t}"').fetchall()]
            for t in _tables(conn)
        }
    finally:
        conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "backup" and len(argv) == 4:
        return cmd_backup(Path(argv[2]), Path(argv[3]))
    if cmd == "counts" and len(argv) == 3:
        return cmd_counts(Path(argv[2]))
    if cmd == "dump" and len(argv) == 4:
        return cmd_dump(Path(argv[2]), Path(argv[3]))
    print(f"ERROR: bad arguments: {argv[1:]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
