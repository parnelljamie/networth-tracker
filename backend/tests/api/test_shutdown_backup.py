from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core import paths
from app.main import app


def test_closing_the_app_writes_a_backup():
    # Runs the real lifespan against the throwaway data dir conftest sets up.
    backups = Path(paths.data_dir()) / "backups"
    for old in backups.glob("networth-*.db"):
        old.unlink()

    with TestClient(app):
        pass  # startup, then shutdown on exit

    assert list(backups.glob("networth-2*.db")), "no backup written on shutdown"
