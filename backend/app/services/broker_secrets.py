"""Broker API keys, kept out of the database.

The database is copied to the phone and into backups (possibly a OneDrive folder), so a key
stored there would travel with it. Instead each key is a small file under `<data_dir>/secrets/`.
On Windows the file is encrypted with DPAPI (CryptProtectData), which ties it to the current
Windows user: another account, or a copy of the file on another machine, can't decrypt it.
Elsewhere (tests, Linux) the file is plain JSON readable only by its owner.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

_DPAPI_MAGIC = b"DPAPI1:"


@dataclass(frozen=True)
class BrokerCredentials:
    api_key: str
    api_secret: str


def _secrets_dir() -> Path:
    d = Path(settings.data_dir) / "secrets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(provider: str, account_id: int) -> Path:
    return _secrets_dir() / f"{provider}-{account_id}.key"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes) -> _Blob:
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _take(blob: _Blob) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob.pbData)

    def _protect(data: bytes) -> bytes:
        out = _Blob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(_blob(data)), None, None, None, None, 0x1, ctypes.byref(out)
        ):
            raise OSError("Windows couldn't encrypt the API key")
        return _DPAPI_MAGIC + _take(out)

    def _unprotect(data: bytes) -> bytes:
        if not data.startswith(_DPAPI_MAGIC):
            return data
        out = _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(_blob(data[len(_DPAPI_MAGIC):])), None, None, None, None, 0x1, ctypes.byref(out)
        ):
            raise OSError("Windows couldn't decrypt the saved API key")
        return _take(out)

else:

    def _protect(data: bytes) -> bytes:
        return data

    def _unprotect(data: bytes) -> bytes:
        return data


def save(provider: str, account_id: int, creds: BrokerCredentials) -> None:
    payload = json.dumps({"api_key": creds.api_key, "api_secret": creds.api_secret}).encode("utf-8")
    path = _path(provider, account_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(_protect(payload))
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    tmp.replace(path)


def load(provider: str, account_id: int) -> BrokerCredentials | None:
    path = _path(provider, account_id)
    if not path.exists():
        return None
    data = json.loads(_unprotect(path.read_bytes()).decode("utf-8"))
    return BrokerCredentials(api_key=data["api_key"], api_secret=data.get("api_secret", ""))


def delete(provider: str, account_id: int) -> None:
    _path(provider, account_id).unlink(missing_ok=True)
