from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.db_pension import DbPensionDetailsIn, DbPensionDetailsOut
from app.schemas.loan import (
    EquityOut,
    LoanDetailsIn,
    LoanDetailsOut,
    LoanSchedule,
    LoanSimulation,
    OverpaymentIn,
    OverpaymentOut,
    RatePeriodIn,
    RatePeriodOut,
    SimulateIn,
)
from app.services import account_service, loan_service

router = APIRouter(prefix="/api", tags=["loans"])


@router.put("/accounts/{account_id}/db-pension", response_model=DbPensionDetailsOut)
def put_db_pension(
    account_id: int, payload: DbPensionDetailsIn, db: Session = Depends(get_db)
) -> DbPensionDetailsOut:
    account = account_service.get_account(db, account_id)
    return account_service.upsert_db_pension_details(db, account, payload)


@router.put("/accounts/{account_id}/loan", response_model=LoanDetailsOut)
def put_loan(account_id: int, payload: LoanDetailsIn, db: Session = Depends(get_db)) -> LoanDetailsOut:
    account = account_service.get_account(db, account_id)
    return account_service.upsert_loan_details(db, account, payload)


@router.get("/accounts/{account_id}/rate-periods", response_model=list[RatePeriodOut])
def list_rate_periods(account_id: int, db: Session = Depends(get_db)) -> list[RatePeriodOut]:
    account_service.get_account(db, account_id)
    return loan_service.list_rate_periods(db, account_id)


@router.post("/accounts/{account_id}/rate-periods", response_model=RatePeriodOut, status_code=201)
def create_rate_period(
    account_id: int, payload: RatePeriodIn, db: Session = Depends(get_db)
) -> RatePeriodOut:
    account = account_service.get_account(db, account_id)
    return loan_service.create_rate_period(db, account, payload)


@router.patch("/rate-periods/{rate_period_id}", response_model=RatePeriodOut)
def update_rate_period(
    rate_period_id: int, payload: RatePeriodIn, db: Session = Depends(get_db)
) -> RatePeriodOut:
    row = loan_service.get_rate_period(db, rate_period_id)
    return loan_service.update_rate_period(db, row, payload)


@router.delete("/rate-periods/{rate_period_id}", status_code=204)
def delete_rate_period(rate_period_id: int, db: Session = Depends(get_db)) -> None:
    row = loan_service.get_rate_period(db, rate_period_id)
    loan_service.delete_rate_period(db, row)


@router.get("/accounts/{account_id}/overpayments", response_model=list[OverpaymentOut])
def list_overpayments(account_id: int, db: Session = Depends(get_db)) -> list[OverpaymentOut]:
    account_service.get_account(db, account_id)
    return loan_service.list_overpayments(db, account_id)


@router.post("/accounts/{account_id}/overpayments", response_model=OverpaymentOut, status_code=201)
def create_overpayment(
    account_id: int, payload: OverpaymentIn, db: Session = Depends(get_db)
) -> OverpaymentOut:
    account = account_service.get_account(db, account_id)
    return loan_service.create_overpayment(db, account, payload)


@router.patch("/overpayments/{overpayment_id}", response_model=OverpaymentOut)
def update_overpayment(
    overpayment_id: int, payload: OverpaymentIn, db: Session = Depends(get_db)
) -> OverpaymentOut:
    row = loan_service.get_overpayment(db, overpayment_id)
    return loan_service.update_overpayment(db, row, payload)


@router.delete("/overpayments/{overpayment_id}", status_code=204)
def delete_overpayment(overpayment_id: int, db: Session = Depends(get_db)) -> None:
    row = loan_service.get_overpayment(db, overpayment_id)
    loan_service.delete_overpayment(db, row)


@router.get("/accounts/{account_id}/schedule", response_model=LoanSchedule)
def get_schedule(
    account_id: int, include_planned: bool = True, db: Session = Depends(get_db)
) -> LoanSchedule:
    account = account_service.get_account(db, account_id)
    return loan_service.schedule(db, account, include_planned=include_planned)


@router.post("/accounts/{account_id}/schedule/simulate", response_model=LoanSimulation)
def simulate_schedule(
    account_id: int, payload: SimulateIn, db: Session = Depends(get_db)
) -> LoanSimulation:
    account = account_service.get_account(db, account_id)
    lump_sums = [(ls.date, ls.amount_gbp) for ls in payload.lump_sums]
    return loan_service.simulate(
        db, account, payload.extra_monthly_gbp, lump_sums, payload.overpayment_effect
    )


@router.post("/accounts/{account_id}/schedule/simulate/save", response_model=list[OverpaymentOut])
def save_simulation(
    account_id: int, payload: SimulateIn, db: Session = Depends(get_db)
) -> list[OverpaymentOut]:
    """Not in docs/04-api.md's literal endpoint list — added so the UI's "Save as plan" action
    (docs/05-ui.md, Phase 4 acceptance) can persist a simulation without recurring_plans, which
    arrives in Phase 5. Persists the simulated overpayments as `loan_overpayments(is_planned=true)`."""
    account = account_service.get_account(db, account_id)
    lump_sums = [(ls.date, ls.amount_gbp) for ls in payload.lump_sums]
    return loan_service.save_simulation_as_plan(db, account, payload.extra_monthly_gbp, lump_sums)


@router.get("/accounts/{account_id}/equity", response_model=EquityOut)
def get_equity(account_id: int, db: Session = Depends(get_db)) -> EquityOut:
    account = account_service.get_account(db, account_id)
    return loan_service.equity(db, account)
