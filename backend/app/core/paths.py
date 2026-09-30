"""Every file path in the app goes through here so Phase 9 packaging needs no path hunting."""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

APP_DIR_NAME = "Waymark"
# The app was called Passbook before the rename; installs from then keep their data here until
# migrate_legacy_data_dir() moves it.
LEGACY_DIR_NAME = "Passbook"


def resource_dir() -> Path:
    """Bundled read-only resources: frontend/dist, alembic/, alembic.ini."""
    override = os.environ.get("NW_RESOURCE_DIR")
    if override:
        # The Android app unpacks them into its private storage (docs/07-mobile.md).
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3]


def _installed_data_root() -> Path:
    """The folder that holds the installed app's data folder, per platform."""
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"])
    # Linux: the XDG data folder, normally ~/.local/share.
    return Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))


def data_dir() -> Path:
    """Where the database, backups and logs live."""
    override = os.environ.get("NW_DATA_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        root = _installed_data_root()
        current, legacy = root / APP_DIR_NAME, root / LEGACY_DIR_NAME
        # Until the Passbook folder has been moved (it can't be while an old copy of the app
        # still has files in it open), keep using it rather than starting from empty.
        if not current.exists() and legacy.exists():
            return legacy
        return current
    return resource_dir() / "data"


def migrate_legacy_data_dir() -> Path | None:
    """Renames the installed app's Passbook data folder to Waymark, once. Returns the new folder
    if it moved anything. Must run before anything reads app.config, which caches data_dir().

    Does nothing when the Waymark folder already exists (both are left alone rather than
    merged), for dev and the phone (they set their own data folder), or when the rename fails,
    typically because an old Passbook.exe still has the database open: data_dir() then keeps
    pointing at the Passbook folder and the next launch tries again."""
    if os.environ.get("NW_DATA_DIR") or not getattr(sys, "frozen", False):
        return None
    root = _installed_data_root()
    current, legacy = root / APP_DIR_NAME, root / LEGACY_DIR_NAME
    if current.exists() or not legacy.is_dir():
        return None
    try:
        legacy.rename(current)
    except OSError:
        return None
    # The old single-instance lock file came along; the app now uses waymark.lock.
    with contextlib.suppress(OSError):
        (current / "passbook.lock").unlink(missing_ok=True)
    return current
