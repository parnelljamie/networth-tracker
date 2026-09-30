from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.enums import Category, Frequency, PlanKind, ValuationMethod, Wrapper
from app.models.people import Person
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.recurring import RecurringPlanCreate
from app.services import account_service, recurring_service, valuation_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def test_balance_account_rolls_forward_expected_contributions(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Workplace pension (balance)",
            category=Category.pension,
            wrapper=Wrapper.workplace_pension,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 8, 1), balance_gbp=10000.0),
        ),
    )
    recurring_service.create_plan(
        db,
        account,
        RecurringPlanCreate(
            account_id=account.id,
            name="Employer + personal",
            kind=PlanKind.contribution,
            amount_gbp=300.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 8, 1),
        ),
    )

    valuation = valuation_service.value_account(db, account, date(2026, 10, 1), live=True)
    # Occurrences on/after 2 Aug through 1 Oct: 1 Sep, 1 Oct -> 2 x 300 = 600 added.
    assert valuation.value_gbp == 10600.0
    assert valuation.is_estimated is True
    assert "expected contributions" in (valuation.detail or "")

    # A fresh balance entry stops the roll-forward.
    from app.models.balances import BalanceEntry

    db.add(BalanceEntry(account_id=account.id, date=date(2026, 10, 1), balance_gbp=11000.0))
    db.commit()
    valuation2 = valuation_service.value_account(db, account, date(2026, 10, 1), live=True)
    assert valuation2.value_gbp == 11000.0
    assert valuation2.is_estimated is False
