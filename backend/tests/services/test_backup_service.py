from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.services import backup_service


@pytest.fixture()
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    source = tmp_path / "networth.db"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    monkeypatch.setattr("app.db.db_path", lambda: source)
    return tmp_path


def test_run_backup_writes_a_dated_file_and_prunes_old_ones(
    db: Session, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    from app.services import settings_service

    monkeypatch.setattr(settings_service, "get", lambda db, key, default=None: 2)

    for i in range(3):
        (isolated_data_dir / "backups").mkdir(exist_ok=True)
        (isolated_data_dir / "backups" / f"networth-2026-01-0{i + 1}.db").write_bytes(b"old")

    path = backup_service.run_backup(db)
    assert path.exists()
    assert path.parent == isolated_data_dir / "backups"

    remaining = sorted((isolated_data_dir / "backups").glob("networth-*.db"))
    assert len(remaining) == 2  # keep=2, newest by filename


def test_list_backups_returns_newest_first(isolated_data_dir: Path):
    backups_dir = isolated_data_dir / "backups"
    backups_dir.mkdir(exist_ok=True)
    (backups_dir / "networth-2026-01-01.db").write_bytes(b"a")
    (backups_dir / "networth-2026-06-01.db").write_bytes(b"bb")

    rows = backup_service.list_backups()
    assert [r.filename for r in rows] == ["networth-2026-06-01.db", "networth-2026-01-01.db"]
    assert rows[1].size_bytes == 1
