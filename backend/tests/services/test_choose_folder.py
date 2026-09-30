from __future__ import annotations

import subprocess
import sys

import pytest

from app.services import system_service

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows folder picker")


def _fake_run(stdout: bytes, seen: dict):
    def run(args, **kwargs):
        seen["args"] = args
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr=b"")

    return run


def test_returns_the_chosen_folder_and_passes_the_start_folder_safely(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(rb"C:\Users\me\OneDrive\Backups", seen))

    chosen = system_service.choose_folder(r"C:\Users\me\OneDrive'; Remove-Item x", "Pick")

    assert chosen == r"C:\Users\me\OneDrive\Backups"
    # The start folder travels in the environment, never inside the PowerShell script itself.
    assert seen["env"]["WAYMARK_PICK_START"] == r"C:\Users\me\OneDrive'; Remove-Item x"
    assert "Remove-Item" not in " ".join(seen["args"])


def test_cancel_returns_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(b"", {}))
    assert system_service.choose_folder() is None
