"""What the /api/sync endpoints need: status, turning the listener on and off, pairing, and the
phone's view of its own sync."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import ConflictError
from app.schemas.sync import (
    PairOut,
    SyncClientOut,
    SyncDeviceOut,
    SyncReportOut,
    SyncStatusOut,
    report_out,
)
from app.services import settings_service
from app.services.sync import client, devices, lan, outbox


def require_role(role: str) -> None:
    if settings.role != role:
        where = "on the PC" if role == "desktop" else "on the phone"
        raise ConflictError(f"That's only available {where}", code="wrong_role")


def _port(db: Session) -> int:
    return int(settings_service.get(db, "sync_port", lan.DEFAULT_PORT))


def desktop_status(db: Session) -> SyncStatusOut:
    require_role("desktop")
    return SyncStatusOut(
        role=settings.role,
        enabled=bool(settings_service.get(db, "sync_enabled", False)),
        running=lan.is_running(),
        port=_port(db),
        addresses=devices.lan_addresses(),
        pc_name=devices.pc_name(),
        devices=[SyncDeviceOut.model_validate(d) for d in devices.list_devices(db)],
    )


def set_enabled(db: Session, enabled: bool, port: int | None = None) -> SyncStatusOut:
    require_role("desktop")
    patch: dict[str, object] = {"sync_enabled": enabled}
    if port is not None:
        patch["sync_port"] = port
    settings_service.update(db, patch)
    if enabled:
        lan.start(_port(db))
    else:
        lan.stop()
    return desktop_status(db)


def start_if_enabled(db: Session) -> None:
    """At startup (desktop only)."""
    if settings.role == "desktop" and settings_service.get(db, "sync_enabled", False):
        lan.start(_port(db))


def pair_phone(db: Session, name: str) -> PairOut:
    require_role("desktop")
    device, token = devices.pair(db, name)
    port = _port(db)
    addresses = devices.lan_addresses()
    return PairOut(
        device_id=device.id,
        token=token,
        pairing_uri=devices.pairing_uri(addresses, port, token, device.id, devices.pc_name()),
        addresses=addresses,
        port=port,
    )


def unpair_phone(db: Session, device_id: int) -> None:
    require_role("desktop")
    devices.unpair(db, device_id)


def client_status(db: Session) -> SyncClientOut:
    require_role("phone")
    cfg = client.load_config()
    return SyncClientOut(
        role=settings.role,
        paired=cfg.paired,
        pc_name=cfg.pc_name or None,
        last_sync_at=cfg.last_sync_at,
        last_attempt_at=cfg.last_attempt_at,
        pending_changes=outbox.pending_count(db),
        last_report=report_out(cfg.last_report),
    )


def client_pair(db: Session, pairing_uri: str) -> SyncClientOut:
    require_role("phone")
    client.pair(pairing_uri)
    return client_status(db)


def client_sync(db: Session) -> SyncReportOut:
    require_role("phone")
    return SyncReportOut(**client.sync_now(db))


def client_forget() -> None:
    require_role("phone")
    client.forget()
