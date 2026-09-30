"""docs/07-mobile.md "Sync server": paired phones and their tokens (only a hash is stored)."""
from __future__ import annotations

import base64
import hashlib
import secrets
import socket
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc_naive
from app.core.errors import DomainError, NotFoundError
from app.models.sync import SyncDevice


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def pc_name() -> str:
    return socket.gethostname() or "PC"


def lan_addresses() -> list[str]:
    """This PC's IPv4 addresses on the home network, best first. The UDP connect sends nothing;
    it only asks the OS which interface would route outwards."""
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(str(info[4][0]))
    except OSError:
        pass
    usable = [a for a in dict.fromkeys(found) if not a.startswith(("127.", "169.254."))]
    return usable


def pairing_uri(hosts: list[str], port: int, token: str, device_id: int, name: str) -> str:
    query = urlencode(
        {"h": ",".join(hosts), "p": port, "t": token, "d": device_id, "n": name}, quote_via=quote
    )
    # Still the pre-rename scheme: phones on 0.5.2 and earlier only accept passbook://.
    return f"passbook://pair?{query}"


def pair(db: Session, name: str) -> tuple[SyncDevice, str]:
    name = name.strip()
    if not name:
        raise DomainError("validation", "Give the phone a name", field="name")
    token = new_token()
    device = SyncDevice(name=name, token_hash=hash_token(token), paired_at=now_utc_naive())
    db.add(device)
    db.commit()
    db.refresh(device)
    return device, token


def list_devices(db: Session) -> list[SyncDevice]:
    return list(
        db.scalars(select(SyncDevice).where(SyncDevice.revoked_at.is_(None)).order_by(SyncDevice.id))
    )


def unpair(db: Session, device_id: int) -> None:
    device = db.get(SyncDevice, device_id)
    if device is None or device.revoked_at is not None:
        raise NotFoundError("That phone isn't paired")
    device.revoked_at = now_utc_naive()
    db.commit()


def authenticate(db: Session, token: str) -> SyncDevice | None:
    if not token:
        return None
    device = db.scalar(select(SyncDevice).where(SyncDevice.token_hash == hash_token(token)))
    if device is None or device.revoked_at is not None:
        return None
    device.last_seen_at = now_utc_naive()
    db.commit()
    return device
