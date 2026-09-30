"""Phase 7: a minimal pywebview window wrapping the local server.

This is NOT the Phase 9 installer entry point (that's `backend/app/launcher.py`, built
later with single-instance locking, port fallback, PyInstaller freezing, etc.). This
script is a simple always-on convenience for running the app during development /
before the installer exists: it builds the frontend if stale (same rule as
scripts/start.ps1), starts Uvicorn on 127.0.0.1 in a background thread, waits for
/api/health, and opens a pywebview window on it. Closing the window stops the server.

Usage:
    uv run python scripts/desktop.py               # normal: opens a window
    uv run python scripts/desktop.py --background   # no window; used by the autostart
                                                      # task so snapshots/backups still run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
HOST = "127.0.0.1"
PORT = 8000
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"


def _latest_mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    files = [p for p in path.rglob("*") if p.is_file()]
    return max((p.stat().st_mtime for p in files), default=None)


def _build_frontend_if_stale() -> None:
    dist_time = _latest_mtime(DIST_DIR)
    src_time = _latest_mtime(FRONTEND_DIR / "src")
    if dist_time is not None and (src_time is None or src_time <= dist_time):
        return
    print("Building frontend...")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)


def _run_server() -> None:
    import uvicorn

    sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app  # noqa: E402  (import after sys.path tweak, mirrors launcher.py's future role)

    uvicorn.run(app, host=HOST, port=PORT, log_config=None)


def _wait_for_health(timeout_s: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run the server only, with no window (used by the logon autostart task).",
    )
    args = parser.parse_args()

    _build_frontend_if_stale()

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    if not _wait_for_health():
        print(f"Server did not answer {HEALTH_URL} within 20s; exiting.", file=sys.stderr)
        sys.exit(1)

    if args.background:
        print(f"Running in background at http://{HOST}:{PORT} (no window). Ctrl+C to stop.")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        return

    import webview

    webview.create_window(
        "Waymark",
        f"http://{HOST}:{PORT}",
        width=1280,
        height=840,
        min_size=(1024, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
