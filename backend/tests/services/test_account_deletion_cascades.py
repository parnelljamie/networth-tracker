"""Deleting an account must never 500 because some other table still points at it.

Account deletion is unrestricted (there is no archive path any more), so every FK aimed at
`accounts.id` / `recurring_plans.id` needs a rule. These tests exercise the three paths that had
none, and rely on `conftest` setting `PRAGMA foreign_keys=ON` so the DB-level rules are real.
"""
from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import (
    Category,
    Frequency,
    PlanKind,
    RateType,
    ScenarioEventKind,
    TxnType,
    ValuationMethod,
    Wrapper,
)
from app.models.accounts import Account
from app.models.loans import LoanDetails
from app.models.people import Person
from app.models.recurring import RecurringPlan
from app.models.scenarios import Scenario, ScenarioEvent
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.loan import LoanDetailsCreate, LoanDetailsIn
from app.services import account_service, loan_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _property(db: Session, owner_id: int) -> Account:
    return account_service.create_account(
        db,
        AccountCreate(
            name="Home",
            category=Category.property,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.model,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 1), balance_gbp=400000.0),
            growth_model={"annual_rate": 0.0, "method": "compound"},
            property={
                "address": "1 Test St",
                "purchase_date": "2026-09-01",
                "purchase_price_gbp": 400000,
            },
        ),
    )


def _mortgage(db: Session, owner_id: int) -> Account:
    return account_service.create_account(
        db,
        AccountCreate(
            name="Mortgage",
            category=Category.mortgage,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.amortising,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            loan=LoanDetailsCreate(
                original_amount_gbp=200000.0,
                start_date=date(2026, 9, 1),
                maturity_date=date(2051, 9, 1),
                fallback_rate=0.045,
                rate_periods=[
                    {
                        "start_date": date(2026, 9, 1),
                        "end_date": None,
                        "annual_rate": 0.045,
                        "rate_type": RateType.fixed,
                    }
                ],
            ),
            initial_balance=InitialBalanceIn(date=date(2026, 9, 1), balance_gbp=200000.0),
        ),
    )


def _cash_account(db: Session, owner_id: int, name: str = "Everyday") -> Account:
    return account_service.create_account(
        db,
        AccountCreate(
            name=name,
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 1), balance_gbp=1000.0),
        ),
    )


def _scenario(db: Session) -> Scenario:
    scenario = db.query(Scenario).first()
    if scenario is None:
        scenario = Scenario(name="Base", is_default=True)
        db.add(scenario)
        db.commit()
        db.refresh(scenario)
    return scenario


def test_delete_property_keeps_mortgage_and_nulls_secured_on_link(db: Session):
    """The mortgage must survive its property; it just becomes unlinked."""
    james = _person(db)
    with freeze_time("2026-09-16"):
        prop = _property(db, james.id)
        mortgage = _mortgage(db, james.id)
        db.refresh(mortgage)
        account_service.upsert_loan_details(
            db,
            mortgage,
            LoanDetailsIn(
                secured_on_account_id=prop.id,
                original_amount_gbp=200000.0,
                start_date=date(2026, 9, 1),
                maturity_date=date(2051, 9, 1),
                fallback_rate=0.045,
            ),
        )
        mortgage_id = mortgage.id

        account_service.delete_account(db, prop)

    assert db.get(Account, mortgage_id) is not None, "mortgage must outlive the property"
    details = db.get(LoanDetails, mortgage_id)
    assert details is not None, "loan_details row must outlive the property"
    assert details.secured_on_account_id is None, "the security link must be cleared, not dangling"


def test_unlinked_mortgage_does_not_break_equity_for_another_property(db: Session):
    """An unlinked mortgage simply stops appearing under any property rather than crashing."""
    james = _person(db)
    with freeze_time("2026-09-16"):
        prop = _property(db, james.id)
        other = _property(db, james.id)
        mortgage = _mortgage(db, james.id)
        db.refresh(mortgage)
        account_service.upsert_loan_details(
            db,
            mortgage,
            LoanDetailsIn(
                secured_on_account_id=prop.id,
                original_amount_gbp=200000.0,
                start_date=date(2026, 9, 1),
                maturity_date=date(2051, 9, 1),
                fallback_rate=0.045,
            ),
        )
        account_service.delete_account(db, prop)
        db.refresh(other)

        equity = loan_service.equity(db, other)

    assert equity["loans"] == []
    assert equity["equity_gbp"] == equity["value_gbp"]


def test_delete_account_removes_scenario_events_targeting_it(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _cash_account(db, james.id)
        scenario = _scenario(db)
        event = ScenarioEvent(
            scenario_id=scenario.id,
            date=date(2027, 1, 1),
            kind=ScenarioEventKind.lump_sum,
            account_id=account.id,
            amount_gbp=5000.0,
            label="Windfall",
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        event_id = event.id

        account_service.delete_account(db, account)

    assert db.get(ScenarioEvent, event_id) is None, "event targeting a deleted account must go"


def test_delete_account_removes_plan_and_scenario_events_referencing_the_plan(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _cash_account(db, james.id)
        plan = RecurringPlan(
            account_id=account.id,
            name="Monthly saving",
            kind=PlanKind.contribution,
            amount_gbp=250.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 9, 1),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        scenario = _scenario(db)
        event = ScenarioEvent(
            scenario_id=scenario.id,
            date=date(2027, 1, 1),
            kind=ScenarioEventKind.stop_plan,
            plan_id=plan.id,
            label="Stop saving",
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        plan_id, event_id = plan.id, event.id

        account_service.delete_account(db, account)

    assert db.get(RecurringPlan, plan_id) is None, "the plan goes with its account"
    assert db.get(ScenarioEvent, event_id) is None, "the event goes with its plan"


def test_deleting_a_plan_keeps_its_recorded_transactions(db: Session):
    """Recorded history outlives the plan that generated it; only the link is cleared."""
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _cash_account(db, james.id)
        plan = RecurringPlan(
            account_id=account.id,
            name="Monthly saving",
            kind=PlanKind.contribution,
            amount_gbp=250.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 9, 1),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        txn = Transaction(
            account_id=account.id,
            date=date(2026, 9, 1),
            type=TxnType.DEPOSIT,
            amount_gbp=250.0,
            recurring_plan_id=plan.id,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        txn_id = txn.id

        db.delete(plan)
        db.commit()

    survivor = db.get(Transaction, txn_id)
    assert survivor is not None, "the transaction must outlive the plan"
    assert survivor.recurring_plan_id is None
