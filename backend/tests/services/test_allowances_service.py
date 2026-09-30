from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import (
    Category,
    ContributionSource,
    Frequency,
    PlanKind,
    TxnSource,
    TxnStatus,
    TxnType,
    ValuationMethod,
    Wrapper,
)
from app.models.people import Person
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.recurring import RecurringPlanCreate
from app.services import account_service, allowances_service, recurring_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def test_allowances_combine_ledger_deposits_and_estimated_plans(db: Session):
    james = _person(db)

    with freeze_time("2026-09-16"):
        isa = account_service.create_account(
            db,
            AccountCreate(
                name="S&S ISA",
                category=Category.investment,
                wrapper=Wrapper.isa,
                valuation_method=ValuationMethod.holdings,
                owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            ),
        )
        db.add(
            Transaction(
                account_id=isa.id,
                date=date(2026, 5, 1),
                type=TxnType.DEPOSIT,
                amount_gbp=5000.0,
                contribution_source=ContributionSource.personal,
                status=TxnStatus.confirmed,
                source=TxnSource.manual,
            )
        )
        db.commit()

        cash_isa = account_service.create_account(
            db,
            AccountCreate(
                name="Cash ISA",
                category=Category.cash,
                wrapper=Wrapper.isa,
                valuation_method=ValuationMethod.balance,
                owners=[OwnerShareIn(person_id=james.id, share=1.0)],
                initial_balance=InitialBalanceIn(date=date(2026, 4, 6), balance_gbp=0.0),
            ),
        )
        recurring_service.create_plan(
            db,
            cash_isa,
            RecurringPlanCreate(
                account_id=cash_isa.id,
                name="Monthly cash ISA",
                kind=PlanKind.contribution,
                amount_gbp=500.0,
                frequency=Frequency.monthly,
                start_date=date(2026, 4, 6),
            ),
        )

        rows = allowances_service.usage(db, person_id=james.id)

    assert len(rows) == 1
    row = rows[0]
    assert row["tax_year"] == "2026/27"
    # 5000 from the ledger deposit + 6 monthly occurrences (Apr..Sep) x 500 = 3000 -> 8000.
    assert row["isa_used"] == 8000.0
    assert row["isa_remaining"] == 20000.0 - 8000.0
    assert row["is_estimated"] is True


def test_pension_relief_at_source_counts_gross_towards_the_annual_allowance(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        sipp = account_service.create_account(
            db,
            AccountCreate(
                name="SIPP (balance)",
                category=Category.pension,
                wrapper=Wrapper.sipp,
                valuation_method=ValuationMethod.balance,
                owners=[OwnerShareIn(person_id=james.id, share=1.0)],
                initial_balance=InitialBalanceIn(date=date(2026, 4, 6), balance_gbp=0.0),
            ),
        )
        recurring_service.create_plan(
            db,
            sipp,
            RecurringPlanCreate(
                account_id=sipp.id,
                name="SIPP contribution",
                kind=PlanKind.contribution,
                amount_gbp=400.0,
                frequency=Frequency.monthly,
                start_date=date(2026, 4, 6),
                tax_relief_rate=0.25,
            ),
        )
        rows = allowances_service.usage(db, person_id=james.id)

    row = rows[0]
    # 6 occurrences (Apr..Sep) x 500 gross = 3000.
    assert row["pension_used"] == 3000.0
