from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.balance import (
    BalanceEntryIn,
    BalanceEntryOut,
    BalanceEntryUpdate,
    BulkBalancesIn,
    BulkBalancesOut,
    QuickUpdateRow,
)
from app.services import account_service, balance_service

router = APIRouter(prefix="/api", tags=["balances"])


@router.get("/accounts/{account_id}/balances", response_model=list[BalanceEntryOut])
def list_balances(account_id: int, db: Session = Depends(get_db)) -> list[BalanceEntryOut]:
    account_service.get_account(db, account_id)
    return balance_service.list_balances(db, account_id)


@router.post("/accounts/{account_id}/balances", response_model=BalanceEntryOut, status_code=201)
def upsert_balance(
    account_id: int, payload: BalanceEntryIn, db: Session = Depends(get_db)
) -> BalanceEntryOut:
    account = account_service.get_account(db, account_id)
    return balance_service.upsert_balance(db, account, payload)


@router.patch("/balances/{entry_id}", response_model=BalanceEntryOut)
def update_balance(
    entry_id: int, payload: BalanceEntryUpdate, db: Session = Depends(get_db)
) -> BalanceEntryOut:
    entry = balance_service.get_balance_entry(db, entry_id)
    return balance_service.update_balance_entry(db, entry, payload)


@router.delete("/balances/{entry_id}", status_code=204)
def delete_balance(entry_id: int, db: Session = Depends(get_db)) -> None:
    entry = balance_service.get_balance_entry(db, entry_id)
    balance_service.delete_balance_entry(db, entry)


@router.get("/balances/quick-update", response_model=list[QuickUpdateRow])
def quick_update(person_id: int | None = None, db: Session = Depends(get_db)) -> list[QuickUpdateRow]:
    return balance_service.quick_update_rows(db, person_id=person_id)


@router.post("/balances/bulk", response_model=BulkBalancesOut)
def bulk_balances(payload: BulkBalancesIn, db: Session = Depends(get_db)) -> BulkBalancesOut:
    saved = balance_service.bulk_save(db, payload.entries)
    return BulkBalancesOut(saved=saved)
