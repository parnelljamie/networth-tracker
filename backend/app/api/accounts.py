from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import Category
from app.db import get_db
from app.schemas.account import (
    AccountCreate,
    AccountDetail,
    AccountSummary,
    AccountUpdate,
    GrowthModelIn,
    GrowthModelOut,
    PropertyDetailsIn,
    PropertyDetailsOut,
)
from app.schemas.insights import XirrOut
from app.schemas.networth import AccountHistoryPoint
from app.services import account_service, insights_service, snapshot_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountSummary])
def list_accounts(
    person_id: int | None = None,
    category: Category | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[AccountSummary]:
    accounts = account_service.list_accounts(
        db, person_id=person_id, category=category, include_archived=include_archived
    )
    on = today()
    scope = {person_id} if person_id is not None else None
    return [account_service.build_account_summary(db, a, on, scope) for a in accounts]


@router.post("", response_model=AccountDetail, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> AccountDetail:
    account = account_service.create_account(db, payload)
    return account_service.build_account_detail(db, account, today())


@router.get("/{account_id}", response_model=AccountDetail)
def get_account(account_id: int, db: Session = Depends(get_db)) -> AccountDetail:
    account = account_service.get_account(db, account_id)
    return account_service.build_account_detail(db, account, today())


@router.patch("/{account_id}", response_model=AccountDetail)
def update_account(account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)) -> AccountDetail:
    account = account_service.get_account(db, account_id)
    account = account_service.update_account(db, account, payload)
    return account_service.build_account_detail(db, account, today())


@router.post("/{account_id}/archive", response_model=AccountDetail)
def archive_account(account_id: int, db: Session = Depends(get_db)) -> AccountDetail:
    account = account_service.get_account(db, account_id)
    account = account_service.set_archived(db, account, True)
    return account_service.build_account_detail(db, account, today())


@router.post("/{account_id}/unarchive", response_model=AccountDetail)
def unarchive_account(account_id: int, db: Session = Depends(get_db)) -> AccountDetail:
    account = account_service.get_account(db, account_id)
    account = account_service.set_archived(db, account, False)
    return account_service.build_account_detail(db, account, today())


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = account_service.get_account(db, account_id)
    account_service.delete_account(db, account)


@router.put("/{account_id}/growth-model", response_model=GrowthModelOut)
def put_growth_model(
    account_id: int, payload: GrowthModelIn, db: Session = Depends(get_db)
) -> GrowthModelOut:
    account = account_service.get_account(db, account_id)
    return account_service.upsert_growth_model(db, account, payload)


@router.put("/{account_id}/property", response_model=PropertyDetailsOut)
def put_property(
    account_id: int, payload: PropertyDetailsIn, db: Session = Depends(get_db)
) -> PropertyDetailsOut:
    account = account_service.get_account(db, account_id)
    return account_service.upsert_property_details(db, account, payload)


@router.get("/{account_id}/history", response_model=list[AccountHistoryPoint])
def get_account_history(
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> list[AccountHistoryPoint]:
    account_service.get_account(db, account_id)
    on = today()
    rows = snapshot_service.account_history(
        db, account_id, date_from or on - timedelta(days=365), date_to or on
    )
    return [
        AccountHistoryPoint(
            date=row.date,
            value_gbp=row.value_gbp,
            cost_basis_gbp=row.cost_basis_gbp,
            net_contributions_gbp=row.net_contributions_gbp,
            is_estimated=row.is_estimated,
        )
        for row in rows
    ]


@router.get("/{account_id}/xirr", response_model=XirrOut)
def get_account_xirr(account_id: int, db: Session = Depends(get_db)) -> XirrOut:
    account = account_service.get_account(db, account_id)
    result = insights_service.account_return(db, account)
    return XirrOut(xirr=result.rate, annualised=result.annualised, since=result.since)
