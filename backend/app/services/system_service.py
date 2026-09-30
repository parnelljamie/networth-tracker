"""Phase 9 task 8: Settings -> Data shows the app version and data folder, with an
"Open folder" button. No DB logic here, just OS/version info."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app import __version__
from app.config import settings
from app.schemas.settings import SystemInfoOut


def get_info() -> SystemInfoOut:
    return SystemInfoOut(version=__version__, data_dir=str(Path(settings.data_dir)))


def open_data_folder() -> None:
    folder = Path(settings.data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]  # noqa: S606
    else:
        subprocess.run(["xdg-open", str(folder)], check=False)  # pragma: no cover


# Windows' own folder picker, run in a separate PowerShell (STA thread, as WinForms dialogs need).
# A throwaway TopMost form owns it so it opens in front of the app window rather than behind it.
# The starting folder arrives via an environment variable, never spliced into the script.
_PICK_FOLDER_PS = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = $env:WAYMARK_PICK_TITLE
$dialog.ShowNewFolderButton = $true
if ($env:WAYMARK_PICK_START -and (Test-Path -LiteralPath $env:WAYMARK_PICK_START)) {
    $dialog.SelectedPath = $env:WAYMARK_PICK_START
}
if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Out.Write($dialog.SelectedPath)
}
$owner.Dispose()
"""


def choose_folder(start: str | None = None, title: str = "Choose a folder") -> str | None:
    """Show the Windows folder picker on this PC and return the chosen path, or None if the
    user cancelled. Blocks until the dialog closes."""
    if sys.platform != "win32":
        return _choose_folder_linux(start, title)
    env = {**os.environ, "WAYMARK_PICK_START": start or str(Path.home()), "WAYMARK_PICK_TITLE": title}
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-Command", _PICK_FOLDER_PS],
        capture_output=True,
        env=env,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    chosen = result.stdout.decode("utf-8", errors="replace").strip()
    return chosen or None


def _choose_folder_linux(start: str | None, title: str) -> str | None:
    """zenity (GNOME and most desktops) or kdialog (KDE). Arguments go in as a list, never
    through a shell, so the start folder can't be interpreted as anything but a path."""
    start_dir = start if start and Path(start).is_dir() else str(Path.home())
    if shutil.which("zenity"):
        args = ["zenity", "--file-selection", "--directory", f"--title={title}",
                f"--filename={start_dir.rstrip('/')}/"]
    elif shutil.which("kdialog"):
        args = ["kdialog", "--title", title, "--getexistingdirectory", start_dir]
    else:
        raise RuntimeError(
            "No folder picker found. Install zenity (sudo apt install zenity) or type the path."
        )
    result = subprocess.run(args, capture_output=True, check=False)
    # Both tools exit non-zero when the user cancels.
    if result.returncode != 0:
        return None
    chosen = result.stdout.decode("utf-8", errors="replace").strip()
    return chosen or None
