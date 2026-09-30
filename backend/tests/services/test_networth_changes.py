from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import Category, ValuationMethod, Wrapper
from app.models.people import Person
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.services import account_service, networth_service, snapshot_service


def _person(db: Session) -> Person:
    person = Person(name="James")
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def test_changes_compare_against_the_right_reference_dates(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Cash",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2025, 9, 15), balance_gbp=100.0),
        ),
    )
    with freeze_time("2025-09-15 12:00:00"):
        snapshot_service.take(db, date(2025, 9, 15))
    with freeze_time("2025-12-31 12:00:00"):
        snapshot_service.take(db, date(2025, 12, 31))
    with freeze_time("2026-08-16 12:00:00"):
        snapshot_service.take(db, date(2026, 8, 16))
    with freeze_time("2026-09-15 12:00:00"):
        snapshot_service.take(db, date(2026, 9, 15))

    with freeze_time("2026-09-16 12:00:00"):
        current = networth_service.get_current(db)

    assert current.changes.day.abs_gbp == 0.0  # yesterday's snapshot equals today's live total
    assert current.changes.ytd.abs_gbp == 0.0  # unchanged since 31 Dec last year
    assert current.changes.year.abs_gbp == 0.0  # unchanged since a year ago
    assert account.id  # keep linter happy


def test_changes_are_null_with_no_snapshot_history(db: Session):
    james = _person(db)
    account_service.create_account(
        db,
        AccountCreate(
            name="Cash",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 15), balance_gbp=100.0),
        ),
    )
    current = networth_service.get_current(db)
    assert current.changes.day.abs_gbp is None
    assert current.changes.year.abs_gbp is None
