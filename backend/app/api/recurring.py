from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.clock import today
from app.db import get_db
from app.schemas.recurring import (
    RecurringPlanCreate,
    RecurringPlanOut,
    RecurringPlanUpdate,
    UpcomingItem,
)
from app.services import account_service, recurring_service

router = APIRouter(prefix="/api", tags=["recurring"])


def _to_out(plan, on: date) -> RecurringPlanOut:
    out = RecurringPlanOut.model_validate(plan)
    out.next_date = recurring_service.next_occurrence(plan, on)
    return out


@router.get("/recurring", response_model=list[RecurringPlanOut])
def list_recurring(
    account_id: int | None = None, person_id: int | None = None, db: Session = Depends(get_db)
) -> list[RecurringPlanOut]:
    on = today()
    plans = recurring_service.list_plans(db, account_id=account_id, person_id=person_id)
    return [_to_out(p, on) for p in plans]


@router.post("/recurring", response_model=RecurringPlanOut, status_code=201)
def create_recurring(payload: RecurringPlanCreate, db: Session = Depends(get_db)) -> RecurringPlanOut:
    account = account_service.get_account(db, payload.account_id)
    plan = recurring_service.create_plan(db, account, payload)
    return _to_out(plan, today())


@router.patch("/recurring/{plan_id}", response_model=RecurringPlanOut)
def update_recurring(
    plan_id: int, payload: RecurringPlanUpdate, db: Session = Depends(get_db)
) -> RecurringPlanOut:
    plan = recurring_service.get_plan(db, plan_id)
    plan = recurring_service.update_plan(db, plan, payload)
    return _to_out(plan, today())


@router.delete("/recurring/{plan_id}", status_code=204)
def delete_recurring(plan_id: int, db: Session = Depends(get_db)) -> None:
    plan = recurring_service.get_plan(db, plan_id)
    recurring_service.delete_plan(db, plan)


@router.get("/recurring/upcoming", response_model=list[UpcomingItem])
def upcoming_recurring(
    days: int = 60, person_id: int | None = None, db: Session = Depends(get_db)
) -> list[UpcomingItem]:
    return recurring_service.upcoming(db, days=days, person_id=person_id)
