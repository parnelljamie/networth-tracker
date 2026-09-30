"""Settings -> Updates: asks GitHub for the latest release and, on the PC, downloads the installer
and runs it.

Releases are published to the public code repo (settings.update_repo) so no token is needed. The only
network calls are the ones the user asks for: the check, and the download after "Update now".
Windows downloads and runs the installer here; the Android shell downloads its APK itself (it
has to hand it to the system installer), and Linux just links to the .deb.
"""
from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal

import httpx

from app import __version__
from app.config import settings
from app.core.errors import DomainError
from app.schemas.settings import UpdateCheckOut, UpdateStatusOut

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com/repos/{repo}/releases/latest"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": f"Waymark/{__version__}"}
TIMEOUT_S = 20.0
# Release asset names, from .github/workflows/release.yml. The Passbook names are what releases
# were called before the rename.
ASSET_PATTERNS = {
    "windows": re.compile(r"^(Waymark|Passbook)Setup-[\d.]+\.exe$"),
    "android": re.compile(r"^(waymark|passbook)-[\d.]+\.apk$"),
    "linux": re.compile(r"^(waymark|passbook)_[\d.]+_amd64\.deb$"),
}

Platform = Literal["windows", "android", "linux"]

_status = UpdateStatusOut(state="idle")
_lock = threading.Lock()


def current_platform() -> Platform:
    if settings.role == "phone":
        return "android"
    return "windows" if sys.platform == "win32" else "linux"


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def _pick_asset(assets: list[dict[str, Any]], platform: Platform) -> dict[str, Any] | None:
    pattern = ASSET_PATTERNS[platform]
    return next((a for a in assets if pattern.match(a.get("name", ""))), None)


def _sha256(asset: dict[str, Any]) -> str | None:
    """GitHub publishes each asset's digest as "sha256:<hex>"."""
    digest = asset.get("digest") or ""
    return digest.removeprefix("sha256:") if digest.startswith("sha256:") else None


def check(client: httpx.Client | None = None) -> UpdateCheckOut:
    platform = current_platform()
    try:
        with client or httpx.Client(timeout=TIMEOUT_S, headers=HEADERS, follow_redirects=True) as http:
            response = http.get(API_URL.format(repo=settings.update_repo))
    except httpx.HTTPError as exc:
        logger.warning("Update check failed: %s", exc)
        raise DomainError("update_unreachable", "Couldn't reach GitHub. Check you're online and try again.") from exc
    if response.status_code == 404:
        raise DomainError("update_unreachable", "No releases have been published yet.")
    if response.status_code != 200:
        raise DomainError("update_unreachable", f"GitHub answered {response.status_code}. Try again later.")

    release = response.json()
    latest = str(release.get("tag_name", "")).removeprefix("v")
    asset = _pick_asset(release.get("assets") or [], platform)
    return UpdateCheckOut(
        current_version=__version__,
        latest_version=latest,
        update_available=bool(latest) and _version_tuple(latest) > _version_tuple(__version__),
        platform=platform,
        release_url=release.get("html_url") or f"https://github.com/{settings.update_repo}/releases/latest",
        notes=release.get("body") or "",
        asset_name=asset["name"] if asset else None,
        asset_url=asset["browser_download_url"] if asset else None,
        asset_sha256=_sha256(asset) if asset else None,
        asset_size=asset.get("size") if asset else None,
        can_install=platform == "windows" and bool(getattr(sys, "frozen", False)),
    )


def get_status() -> UpdateStatusOut:
    with _lock:
        return _status.model_copy()


def _set_status(**fields: Any) -> None:
    global _status
    with _lock:
        _status = _status.model_copy(update=fields)


def start_install() -> UpdateStatusOut:
    """Windows only: check again, then download and run the installer in a background thread.
    The installer closes this app, upgrades in place and reopens it (packaging/waymark.iss)."""
    if current_platform() != "windows":
        raise DomainError("update_unsupported", "Updates install from the app only on Windows.")
    if not getattr(sys, "frozen", False):
        raise DomainError("update_unsupported", "This is a development copy; updates install only into the installed app.")
    with _lock:
        if _status.state in ("downloading", "installing"):
            return _status.model_copy()
    info = check()
    if not info.update_available:
        raise DomainError("update_current", f"You're already on the latest version ({info.current_version}).")
    if not info.asset_url:
        raise DomainError("update_missing", "The latest release has no Windows installer.")
    _set_status(state="downloading", version=info.latest_version, downloaded=0, total=info.asset_size, error=None)
    threading.Thread(target=_download_and_run, args=(info,), name="update-install", daemon=True).start()
    return get_status()


def _download_and_run(info: UpdateCheckOut, client: httpx.Client | None = None) -> None:
    try:
        target = download(info, client)
        _set_status(state="installing")
        run_installer(target)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        logger.exception("Update failed")
        _set_status(state="error", error=str(exc) or exc.__class__.__name__)


def download(info: UpdateCheckOut, client: httpx.Client | None = None) -> Path:
    """Streams the installer to a temp folder, checking it against GitHub's SHA-256."""
    assert info.asset_url and info.asset_name
    folder = Path(tempfile.gettempdir()) / "waymark-update"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info.asset_name
    digest = hashlib.sha256()
    http = client or httpx.Client(timeout=TIMEOUT_S, headers=HEADERS, follow_redirects=True)
    with http, http.stream("GET", info.asset_url) as response, target.open("wb") as out:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or info.asset_size or 0) or None
        done = 0
        for chunk in response.iter_bytes(1 << 16):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            _set_status(downloaded=done, total=total)
    if info.asset_sha256 and digest.hexdigest() != info.asset_sha256.lower():
        target.unlink(missing_ok=True)
        raise RuntimeError("The download didn't match GitHub's checksum, so it wasn't installed. Try again.")
    return target


def run_installer(path: Path) -> None:  # pragma: no cover - launches a real installer
    """Starts the installer detached from this process, which it is about to close."""
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    subprocess.Popen(  # noqa: S603
        [str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=flags,
        close_fds=True,
    )
