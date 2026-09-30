from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.instruments import get_price_provider
from app.db import get_db
from app.providers.base import PriceProvider
from app.schemas.imports import ReconciliationRow, UnmatchedInstrument
from app.schemas.trading212 import (
    Trading212ChangeRow,
    Trading212ChangesOut,
    Trading212ConnectIn,
    Trading212LinkOut,
    Trading212LinkUpdate,
    Trading212NewAccountIn,
)
from app.services import trading212_service

router = APIRouter(prefix="/api/trading212", tags=["trading212"])


def _changes_out(changes: trading212_service.PendingChanges) -> Trading212ChangesOut:
    preview = changes.preview
    return Trading212ChangesOut(
        account_id=changes.link.account_id,
        account_name=changes.account_name,
        batch_id=changes.batch_id,
        first_sync=changes.first_sync,
        message=changes.link.status_message,
        transactions=[
            Trading212ChangeRow(
                date=r.date, type=r.type, symbol=r.symbol, name=r.name, units=r.units, amount_gbp=r.amount_gbp
            )
            for r in sorted(changes.rows, key=lambda r: r.date, reverse=True)
        ],
        holdings=[
            ReconciliationRow(**vars(r))
            for r in preview.reconciliation
            if abs(r.units_diff) > 1e-9 or abs(r.avg_cost_diff_gbp) > 0.005
        ],
        cash_before_gbp=changes.cash_before_gbp,
        cash_after_gbp=changes.cash_after_gbp,
        unmatched_instruments=[UnmatchedInstrument(**vars(u)) for u in preview.unmatched_instruments],
        ledger_warnings=preview.ledger_warnings,
        ready=preview.ready,
    )


@router.get("/links", response_model=list[Trading212LinkOut])
def list_links(db: Session = Depends(get_db)) -> list[Trading212LinkOut]:
    return [Trading212LinkOut.model_validate(link) for link in trading212_service.list_links(db)]


@router.post("/sync", response_model=list[Trading212LinkOut], status_code=202)
def sync_all(
    db: Session = Depends(get_db), provider: PriceProvider = Depends(get_price_provider)
) -> list[Trading212LinkOut]:
    return [Trading212LinkOut.model_validate(link) for link in trading212_service.start_sync_all(db, provider)]


@router.get("/changes", response_model=list[Trading212ChangesOut])
def list_changes(db: Session = Depends(get_db)) -> list[Trading212ChangesOut]:
    return [_changes_out(c) for c in trading212_service.list_pending_changes(db)]


@router.post("/links", response_model=Trading212LinkOut, status_code=201)
def connect_new_account(payload: Trading212NewAccountIn, db: Session = Depends(get_db)) -> Trading212LinkOut:
    link = trading212_service.connect_new_account(
        db,
        payload.account_type,
        payload.owner_person_id,
        payload.api_key,
        payload.api_secret,
        payload.environment,
        payload.name,
    )
    return Trading212LinkOut.model_validate(link)


@router.get("/links/{account_id}", response_model=Trading212LinkOut | None)
def get_link(account_id: int, db: Session = Depends(get_db)) -> Trading212LinkOut | None:
    link = trading212_service.get_link(db, account_id)
    return Trading212LinkOut.model_validate(link) if link is not None else None


@router.put("/links/{account_id}", response_model=Trading212LinkOut)
def connect(account_id: int, payload: Trading212ConnectIn, db: Session = Depends(get_db)) -> Trading212LinkOut:
    link = trading212_service.connect(db, account_id, payload.api_key, payload.api_secret, payload.environment)
    return Trading212LinkOut.model_validate(link)


@router.patch("/links/{account_id}", response_model=Trading212LinkOut)
def update_link(
    account_id: int, payload: Trading212LinkUpdate, db: Session = Depends(get_db)
) -> Trading212LinkOut:
    return Trading212LinkOut.model_validate(trading212_service.set_auto_sync(db, account_id, payload.auto_sync))


@router.delete("/links/{account_id}", status_code=204)
def disconnect(account_id: int, db: Session = Depends(get_db)) -> Response:
    trading212_service.disconnect(db, account_id)
    return Response(status_code=204)


@router.post("/links/{account_id}/sync", response_model=Trading212LinkOut, status_code=202)
def sync(
    account_id: int, db: Session = Depends(get_db), provider: PriceProvider = Depends(get_price_provider)
) -> Trading212LinkOut:
    return Trading212LinkOut.model_validate(trading212_service.start_sync(db, account_id, provider))


@router.post("/links/{account_id}/accept", response_model=Trading212LinkOut)
def accept(
    account_id: int, db: Session = Depends(get_db), provider: PriceProvider = Depends(get_price_provider)
) -> Trading212LinkOut:
    return Trading212LinkOut.model_validate(trading212_service.accept(db, account_id, provider))
