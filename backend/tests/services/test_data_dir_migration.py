"""The rename from Passbook to Waymark: the installed app's data folder moves once, on the first
launch of a Waymark build, and nothing is lost if it can't move yet."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core import paths


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A frozen build whose per-user data root is tmp_path."""
    monkeypatch.delenv("NW_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths, "_installed_data_root", lambda: tmp_path)
    return tmp_path


def _legacy(root: Path) -> Path:
    legacy = root / "Passbook"
    (legacy / "backups").mkdir(parents=True)
    (legacy / "networth.db").write_bytes(b"db")
    (legacy / "passbook.lock").write_bytes(b"")
    return legacy


def test_fresh_install_uses_waymark(installed: Path) -> None:
    assert paths.migrate_legacy_data_dir() is None
    assert paths.data_dir() == installed / "Waymark"


def test_moves_the_passbook_folder_once(installed: Path) -> None:
    _legacy(installed)
    assert paths.migrate_legacy_data_dir() == installed / "Waymark"
    assert not (installed / "Passbook").exists()
    assert (installed / "Waymark" / "networth.db").read_bytes() == b"db"
    assert (installed / "Waymark" / "backups").is_dir()
    assert not (installed / "Waymark" / "passbook.lock").exists()
    assert paths.data_dir() == installed / "Waymark"
    assert paths.migrate_legacy_data_dir() is None


def test_keeps_using_passbook_while_it_cannot_move(installed: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = _legacy(installed)

    def locked(self: Path, target: Path) -> Path:
        raise PermissionError("in use by Passbook.exe")

    monkeypatch.setattr(Path, "rename", locked)
    assert paths.migrate_legacy_data_dir() is None
    assert paths.data_dir() == legacy


def test_never_merges_into_an_existing_waymark_folder(installed: Path) -> None:
    legacy = _legacy(installed)
    (installed / "Waymark").mkdir()
    assert paths.migrate_legacy_data_dir() is None
    assert (legacy / "networth.db").exists()
    assert paths.data_dir() == installed / "Waymark"


def test_dev_and_phone_are_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "_installed_data_root", lambda: tmp_path)
    _legacy(tmp_path)
    monkeypatch.setenv("NW_DATA_DIR", str(tmp_path / "phone"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.migrate_legacy_data_dir() is None
    monkeypatch.delenv("NW_DATA_DIR")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert paths.migrate_legacy_data_dir() is None
    assert (tmp_path / "Passbook").exists()
