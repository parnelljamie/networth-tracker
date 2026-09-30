from __future__ import annotations

from datetime import date

import pytest
from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import Category, ValuationMethod, Wrapper
from app.core.errors import DomainError
from app.models.people import Person
from app.schemas.account import AccountCreate, OwnerShareIn
from app.schemas.db_pension import DbPensionDetailsIn
from app.services import account_service, db_pension_service, projection_service, valuation_service


def _person(db: Session) -> Person:
    person = Person(name="Sam", date_of_birth=date(1994, 3, 10))
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _tps(db: Session, owner_id: int):
    return account_service.create_account(
        db,
        AccountCreate(
            name="Teachers' Pension",
            category=Category.pension,
            wrapper=Wrapper.db_pension,
            valuation_method=ValuationMethod.defined_benefit,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            db_pension=DbPensionDetailsIn(
                accrued_annual_pension_gbp=6000.0,
                accrued_as_of=date(2026, 9, 18),
                accrual_rate=1 / 57,
                revaluation_above_cpi=0.016,
                pensionable_salary_gbp=38000.0,
                normal_pension_age=68,
            ),
        ),
    )


def test_tps_account_is_valued_at_20x_the_yearly_pension_and_counts_in_net_worth(db: Session):
    sam = _person(db)
    with freeze_time("2026-09-18"):
        account = _tps(db, sam.id)
        valuation = valuation_service.value_account(db, account, date(2026, 9, 18), live=True)
        summary = db_pension_service.summary(db, account)

    assert account.include_in_networth is True
    assert valuation.value_gbp == pytest.approx(120_000.0)
    assert summary.annual_pension_today_gbp == pytest.approx(6000.0)
    assert summary.pension_start_date == date(2062, 3, 10)
    assert summary.annual_pension_at_start_gbp > 6000.0


def test_db_pension_grows_in_the_projection(db: Session):
    sam = _person(db)
    with freeze_time("2026-09-18"):
        account = _tps(db, sam.id)
        projection = projection_service.build_projection(db, months=120, by_account=True)
    series = projection["by_account"][account.id]
    assert series[0] == pytest.approx(120_000.0)
    assert series[-1] > series[0]


def test_defined_benefit_method_requires_scheme_details(db: Session):
    sam = _person(db)
    with pytest.raises(DomainError):
        account_service.create_account(
            db,
            AccountCreate(
                name="TPS",
                category=Category.pension,
                wrapper=Wrapper.db_pension,
                valuation_method=ValuationMethod.defined_benefit,
                owners=[OwnerShareIn(person_id=sam.id, share=1.0)],
            ),
        )
