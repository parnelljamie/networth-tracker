"""Phase 9 entry point for the frozen app. Builds to `Waymark.exe` via
packaging/waymark.spec. This supersedes scripts/desktop.py (Phase 7's dev/pre-installer
convenience, kept as-is for `uv run python scripts/desktop.py` during development) by
adding single-instance locking, OS-assigned port fallback, and being the actual
PyInstaller entry point.

Usage (frozen or `uv run python -m app.launcher` from backend/):
    Waymark.exe                 # normal: opens a window (attaches to an existing
                                 # server's window if one is already running)
    Waymark.exe --background    # server + scheduler only, no window

On Linux the installed command is `waymark`, which also takes `--autostart on|off`.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Allow running unfrozen via `uv run python -m app.launcher` from backend/, where `app`
# is already importable, and when frozen, PyInstaller puts everything on sys.path itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import paths  # noqa: E402

HOST = "127.0.0.1"
PREFERRED_PORT = 8765
HEALTH_TIMEOUT_S = 20.0

logger = logging.getLogger("app.launcher")

# Keeps the OS-level lock alive for the life of the process; must not be garbage collected.
_lock_handle = None


def _server_json_path() -> Path:
    return paths.data_dir() / "server.json"


def _lock_path() -> Path:
    return paths.data_dir() / "waymark.lock"


def _health_url(port: int) -> str:
    return f"http://{HOST}:{port}/api/health"


def _ping_health(port: int, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(_health_url(port), timeout=timeout) as resp:
            return resp.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _read_server_json() -> dict | None:
    path = _server_json_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_server_json(port: int) -> None:
    _server_json_path().write_text(json.dumps({"port": port, "pid": os.getpid()}))


def _acquire_single_instance_lock() -> bool:
    """Returns True if this process now owns the lock (i.e. is the primary instance)."""
    global _lock_handle
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    lock_path = _lock_path()
    try:
        if sys.platform == "win32":
            import msvcrt

            _lock_handle = open(lock_path, "a+b")  # noqa: SIM115 - kept open for process lifetime
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover - dev convenience on non-Windows
            import fcntl

            _lock_handle = open(lock_path, "a+b")  # noqa: SIM115 - kept open for process lifetime
            fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        if _lock_handle is not None:
            _lock_handle.close()
            _lock_handle = None
        return False


def _release_single_instance_lock() -> None:
    global _lock_handle
    if _lock_handle is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            _lock_handle.seek(0)
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover
            import fcntl

            fcntl.flock(_lock_handle, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        _lock_handle.close()
        _lock_handle = None


def _pick_port() -> int:
    for candidate in (PREFERRED_PORT,):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((HOST, candidate))
            sock.close()
            return candidate
        except OSError:
            sock.close()
    # Fall back to an OS-assigned free port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _configure_logging() -> Path:
    logs_dir = paths.data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "launcher.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )
    return log_file


def _run_server(port: int) -> None:
    import uvicorn

    from app.main import app

    uvicorn.run(
        app,
        host=HOST,
        port=port,
        log_config=None,
    )


def _wait_for_health(port: int, timeout_s: float = HEALTH_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _ping_health(port):
            return True
        time.sleep(0.3)
    return False


def _show_native_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, message, "Waymark", 0x10)  # MB_ICONERROR
    else:  # pragma: no cover
        print(message, file=sys.stderr)
        # Best effort: a desktop dialog, since the installed app has no terminal attached.
        import shutil
        import subprocess

        if shutil.which("zenity"):
            subprocess.run(["zenity", "--error", "--title=Waymark", f"--text={message}"], check=False)
        elif shutil.which("kdialog"):
            subprocess.run(["kdialog", "--title", "Waymark", "--error", message], check=False)


def _open_window(port: int) -> None:
    import webview

    def _on_closed() -> None:
        # Only the primary instance's window exit should end the process; a
        # window opened by an attaching instance just needs to let this
        # process (which never started a server) exit naturally too.
        pass

    window = webview.create_window(
        "Waymark",
        f"http://{HOST}:{port}",
        width=1280,
        height=840,
        min_size=(1024, 700),
    )
    window.events.closed += _on_closed
    # Linux builds bundle Qt WebEngine (packaging/waymark.spec) rather than relying on the
    # system's GTK WebKit, so ask for Qt explicitly instead of letting pywebview try GTK first.
    webview.start(gui="qt" if sys.platform.startswith("linux") else None)


def _autostart_file(name: str = "waymark") -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "autostart" / f"{name}.desktop"


def _set_autostart(enabled: bool) -> None:
    """Linux counterpart of the Windows installer's "start when I sign in" option: an XDG
    autostart entry that runs the server in the background at login."""
    target = _autostart_file()
    if enabled:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Waymark (background)\n"
            f"Exec={sys.executable} --background\n"
            "X-GNOME-Autostart-enabled=true\n"
            "NoDisplay=true\n"
        )
        print(f"Waymark will start in the background when you log in ({target}).")
    else:
        target.unlink(missing_ok=True)
        print("Waymark will no longer start when you log in.")


def _migrate_from_passbook() -> Path | None:
    """First launch after the rename: move the Passbook data folder, and on Linux swap an
    autostart entry that runs /opt/passbook/passbook (removed with the old package) for one
    that runs this executable. The Windows installer handles the Run key itself."""
    moved = paths.migrate_legacy_data_dir()
    legacy_autostart = _autostart_file("passbook")
    if sys.platform.startswith("linux") and getattr(sys, "frozen", False) and legacy_autostart.exists():
        legacy_autostart.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            _set_autostart(True)
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run the server and scheduler only, with no window (used at sign-in).",
    )
    if sys.platform.startswith("linux"):
        parser.add_argument(
            "--autostart",
            choices=["on", "off"],
            help="Start Waymark in the background when you log in (on) or stop doing so (off).",
        )
    args = parser.parse_args()

    if getattr(args, "autostart", None):
        _set_autostart(args.autostart == "on")
        return

    # Before logging (which writes into the data folder) and before anything imports app.config.
    moved = _migrate_from_passbook()
    log_file = _configure_logging()
    logger.info("Waymark launcher starting, background=%s", args.background)
    if moved:
        logger.info("Moved the data folder from Passbook to %s", moved)

    # If another instance is already answering /api/health, attach a window to it
    # (or, in --background mode, simply exit) instead of starting a second server.
    existing = _read_server_json()
    if existing and _ping_health(existing.get("port", -1)):
        logger.info("Existing instance found on port %s", existing["port"])
        if not args.background:
            _open_window(existing["port"])
        return

    if not _acquire_single_instance_lock():
        # Another process is starting up right now (lost the race for the lock).
        # Give it a moment to publish server.json and answer health, then attach.
        for _ in range(20):
            time.sleep(0.5)
            existing = _read_server_json()
            if existing and _ping_health(existing.get("port", -1)):
                if not args.background:
                    _open_window(existing["port"])
                return
        logger.warning("Could not acquire single-instance lock and no server answered; exiting.")
        return

    try:
        port = _pick_port()
        logger.info("Starting server on %s:%s", HOST, port)
        _write_server_json(port)

        server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
        server_thread.start()

        if not _wait_for_health(port):
            _show_native_error(
                f"Waymark's server did not start within {int(HEALTH_TIMEOUT_S)} seconds.\n"
                f"See the log file for details:\n{log_file}"
            )
            return

        if args.background:
            logger.info("Running in background (no window). PID=%s", os.getpid())
            server_thread.join()
            return

        _open_window(port)
        logger.info("Window closed; shutting down.")
        # The server runs on a daemon thread that dies with this process, so its own shutdown
        # hook never runs here: take the closing backup explicitly.
        from app.jobs import backup_job

        backup_job()
    finally:
        with contextlib.suppress(OSError):
            _server_json_path().unlink(missing_ok=True)
        _release_single_instance_lock()


if __name__ == "__main__":
    main()
