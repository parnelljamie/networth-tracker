"""docs/07-mobile.md: pairing on the PC and syncing on the phone. The PC's LAN-facing sync
endpoints live in a separate app (`app.services.sync.lan`)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.sync import (
    PairIn,
    PairOut,
    SyncClientOut,
    SyncClientPairIn,
    SyncEnabledIn,
    SyncReportOut,
    SyncStatusOut,
)
from app.services.sync import control

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusOut)
def get_status(db: Session = Depends(get_db)) -> SyncStatusOut:
    return control.desktop_status(db)


@router.put("/enabled", response_model=SyncStatusOut)
def set_enabled(payload: SyncEnabledIn, db: Session = Depends(get_db)) -> SyncStatusOut:
    return control.set_enabled(db, payload.enabled, payload.port)


@router.post("/pair", response_model=PairOut, status_code=201)
def pair(payload: PairIn, db: Session = Depends(get_db)) -> PairOut:
    return control.pair_phone(db, payload.name)


@router.delete("/devices/{device_id}", status_code=204)
def unpair(device_id: int, db: Session = Depends(get_db)) -> None:
    control.unpair_phone(db, device_id)


@router.get("/client", response_model=SyncClientOut)
def client_status(db: Session = Depends(get_db)) -> SyncClientOut:
    return control.client_status(db)


@router.post("/client/pair", response_model=SyncClientOut)
def client_pair(payload: SyncClientPairIn, db: Session = Depends(get_db)) -> SyncClientOut:
    return control.client_pair(db, payload.pairing_uri)


@router.post("/client/sync", response_model=SyncReportOut)
def client_sync(db: Session = Depends(get_db)) -> SyncReportOut:
    return control.client_sync(db)


@router.delete("/client", status_code=204)
def client_forget() -> None:
    control.client_forget()
