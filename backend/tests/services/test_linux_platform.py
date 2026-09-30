"""The Linux build's platform-specific bits: the zenity/kdialog folder picker and the XDG
data folder. Pure mocking, so these run on any OS."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.core import paths
from app.services import system_service


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")


def _fake_run(returncode: int, stdout: bytes, seen: dict):
    def run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=b"")

    return run


def _only(tool: str):
    return lambda name: f"/usr/bin/{name}" if name == tool else None


def test_zenity_returns_the_chosen_folder(tmp_path, linux, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(system_service.shutil, "which", _only("zenity"))
    monkeypatch.setattr(subprocess, "run", _fake_run(0, b"/home/me/Backups\n", seen))

    chosen = system_service.choose_folder(str(tmp_path), "Pick")

    assert chosen == "/home/me/Backups"
    assert seen["args"][:3] == ["zenity", "--file-selection", "--directory"]
    assert "--title=Pick" in seen["args"]


def test_kdialog_is_used_when_zenity_is_missing(linux, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(system_service.shutil, "which", _only("kdialog"))
    monkeypatch.setattr(subprocess, "run", _fake_run(0, b"/home/me/Backups", seen))

    assert system_service.choose_folder(None, "Pick") == "/home/me/Backups"
    assert seen["args"][0] == "kdialog"
    assert "--getexistingdirectory" in seen["args"]


def test_cancel_returns_none(linux, monkeypatch):
    monkeypatch.setattr(system_service.shutil, "which", _only("zenity"))
    monkeypatch.setattr(subprocess, "run", _fake_run(1, b"", {}))
    assert system_service.choose_folder() is None


def test_no_picker_installed_explains_what_to_install(linux, monkeypatch):
    monkeypatch.setattr(system_service.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="zenity"):
        system_service.choose_folder()


def test_frozen_linux_data_dir_follows_xdg(tmp_path, linux, monkeypatch):
    monkeypatch.delenv("NW_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path / "Waymark"

    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert paths.data_dir() == tmp_path / "home" / ".local" / "share" / "Waymark"
