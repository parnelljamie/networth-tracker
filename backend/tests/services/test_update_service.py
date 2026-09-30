"""Settings -> Updates, against canned GitHub responses."""
from __future__ import annotations

import hashlib

import httpx
import pytest

from app import __version__
from app.config import settings
from app.core.errors import DomainError
from app.services import update_service

PAYLOAD = b"pretend installer"


def _release(tag: str) -> dict:
    v = tag.removeprefix("v")
    base = f"https://github.com/o/r/releases/download/{tag}"
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/o/r/releases/tag/{tag}",
        "body": "Notes",
        "assets": [
            {"name": f"waymark_{v}_amd64.deb", "browser_download_url": f"{base}/waymark_{v}_amd64.deb", "size": 3},
            {
                "name": f"WaymarkSetup-{v}.0.exe",
                "browser_download_url": f"{base}/WaymarkSetup-{v}.0.exe",
                "size": len(PAYLOAD),
                "digest": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest(),
            },
            {"name": f"waymark-{v}.apk", "browser_download_url": f"{base}/waymark-{v}.apk", "size": 5},
        ],
    }


def _client(handler) -> httpx.Client:  # noqa: ANN001
    return httpx.Client(transport=httpx.MockTransport(handler))


def _bump(version: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


@pytest.fixture
def platform(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    def set_platform(role: str, sys_platform: str) -> None:
        monkeypatch.setattr(settings, "role", role)
        monkeypatch.setattr(update_service.sys, "platform", sys_platform)

    return set_platform


def test_newer_release_offers_the_windows_installer(platform) -> None:  # noqa: ANN001
    platform("desktop", "win32")
    newer = _bump(__version__)
    info = update_service.check(_client(lambda req: httpx.Response(200, json=_release(f"v{newer}"))))
    assert info.update_available
    assert info.latest_version == newer
    assert info.platform == "windows"
    assert info.asset_name == f"WaymarkSetup-{newer}.0.exe"
    assert info.asset_sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert not info.can_install  # tests don't run frozen


@pytest.mark.parametrize(("role", "sys_platform", "suffix"), [("phone", "linux", ".apk"), ("desktop", "linux", ".deb")])
def test_picks_the_asset_for_this_platform(platform, role: str, sys_platform: str, suffix: str) -> None:  # noqa: ANN001
    platform(role, sys_platform)
    info = update_service.check(_client(lambda req: httpx.Response(200, json=_release("v9.0.0"))))
    assert info.asset_name and info.asset_name.endswith(suffix)


@pytest.mark.parametrize(
    ("role", "sys_platform", "name"),
    [("desktop", "win32", "PassbookSetup-9.0.0.exe"), ("phone", "linux", "passbook-9.0.0.apk"), ("desktop", "linux", "passbook_9.0.0_amd64.deb")],
)
def test_still_recognises_pre_rename_asset_names(platform, role: str, sys_platform: str, name: str) -> None:  # noqa: ANN001
    platform(role, sys_platform)
    release = {"tag_name": "v9.0.0", "assets": [{"name": name, "browser_download_url": f"https://x/{name}"}]}
    info = update_service.check(_client(lambda req: httpx.Response(200, json=release)))
    assert info.asset_name == name


def test_same_or_older_release_is_not_an_update(platform) -> None:  # noqa: ANN001
    platform("desktop", "win32")
    info = update_service.check(_client(lambda req: httpx.Response(200, json=_release(f"v{__version__}"))))
    assert not info.update_available
    info = update_service.check(_client(lambda req: httpx.Response(200, json=_release("v0.0.9"))))
    assert not info.update_available


def test_versions_compare_numerically() -> None:
    assert update_service._version_tuple("0.10.0") > update_service._version_tuple("0.9.9")


def test_no_releases_or_offline_is_a_friendly_error(platform) -> None:  # noqa: ANN001
    platform("desktop", "win32")
    with pytest.raises(DomainError, match="No releases"):
        update_service.check(_client(lambda req: httpx.Response(404)))

    def offline(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=req)

    with pytest.raises(DomainError, match="Couldn't reach GitHub"):
        update_service.check(_client(offline))


def test_download_checks_the_sha256(platform, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    platform("desktop", "win32")
    monkeypatch.setattr(update_service.tempfile, "gettempdir", lambda: str(tmp_path))
    info = update_service.check(_client(lambda req: httpx.Response(200, json=_release("v9.0.0"))))

    path = update_service.download(info, _client(lambda req: httpx.Response(200, content=PAYLOAD)))
    assert path.read_bytes() == PAYLOAD

    with pytest.raises(RuntimeError, match="checksum"):
        update_service.download(info, _client(lambda req: httpx.Response(200, content=b"tampered")))
    assert not path.exists()


def test_install_is_refused_outside_the_installed_windows_app(platform) -> None:  # noqa: ANN001
    platform("phone", "linux")
    with pytest.raises(DomainError, match="only on Windows"):
        update_service.start_install()
    platform("desktop", "win32")
    with pytest.raises(DomainError, match="development copy"):
        update_service.start_install()
