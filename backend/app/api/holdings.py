from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import TxnStatus, TxnType
from app.db import get_db
from app.schemas.holdings import Holdings, SetCashIn, SetHoldingIn
from app.schemas.transaction import (
    ConfirmRequest,
    TransactionCreate,
    TransactionListOut,
    TransactionOut,
    TransactionUpdate,
)
from app.services import account_service, holdings_service, ledger_service

router = APIRouter(prefix="/api", tags=["holdings"])


@router.get("/accounts/{account_id}/holdings", response_model=Holdings)
def get_holdings(account_id: int, db: Session = Depends(get_db)) -> Holdings:
    account = account_service.get_account(db, account_id)
    return holdings_service.build_holdings(db, account)


@router.put("/accounts/{account_id}/holdings/{instrument_id}", response_model=Holdings)
def set_holding(
    account_id: int, instrument_id: int, payload: SetHoldingIn, db: Session = Depends(get_db)
) -> Holdings:
    account = account_service.get_account(db, account_id)
    ledger_service.set_position_target(
        db, account_id, instrument_id, payload.units, payload.avg_cost_gbp, payload.as_of
    )
    return holdings_service.build_holdings(db, account)


@router.delete("/accounts/{account_id}/holdings/{instrument_id}", response_model=Holdings)
def delete_holding(account_id: int, instrument_id: int, db: Session = Depends(get_db)) -> Holdings:
    account = account_service.get_account(db, account_id)
    ledger_service.remove_holding(db, account_id, instrument_id)
    return holdings_service.build_holdings(db, account)


@router.put("/accounts/{account_id}/cash", response_model=Holdings)
def set_cash(account_id: int, payload: SetCashIn, db: Session = Depends(get_db)) -> Holdings:
    account = account_service.get_account(db, account_id)
    ledger_service.set_cash_target(db, account_id, payload.cash_gbp, payload.as_of)
    return holdings_service.build_holdings(db, account)


@router.get("/accounts/{account_id}/transactions", response_model=TransactionListOut)
def list_transactions(
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    type: TxnType | None = None,
    status: TxnStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> TransactionListOut:
    account_service.get_account(db, account_id)
    items, total = ledger_service.list_transactions(
        db, account_id, date_from, date_to, type, status, limit, offset
    )
    return TransactionListOut(items=items, total=total)


@router.post("/accounts/{account_id}/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(
    account_id: int, payload: TransactionCreate, db: Session = Depends(get_db)
) -> TransactionOut:
    account_service.get_account(db, account_id)
    return ledger_service.create_transaction(db, account_id, payload)


@router.patch("/transactions/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int, payload: TransactionUpdate, db: Session = Depends(get_db)
) -> TransactionOut:
    txn = ledger_service.get_transaction(db, txn_id)
    return ledger_service.update_transaction(db, txn, payload)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, db: Session = Depends(get_db)) -> None:
    txn = ledger_service.get_transaction(db, txn_id)
    ledger_service.delete_transaction(db, txn)


@router.get("/transactions/pending", response_model=list[TransactionOut])
def pending_transactions(db: Session = Depends(get_db)) -> list[TransactionOut]:
    return ledger_service.list_pending(db)


@router.post("/transactions/confirm", response_model=list[TransactionOut])
def confirm_transactions(payload: ConfirmRequest, db: Session = Depends(get_db)) -> list[TransactionOut]:
    return ledger_service.confirm_pending(db, payload.items)
