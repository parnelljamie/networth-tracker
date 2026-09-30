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
    ValuationMethod,
    Wrapper,
)
from app.models.people import Person
from app.schemas.account import (
    AccountCreate,
    GrowthModelIn,
    InitialBalanceIn,
    OwnerShareIn,
    PropertyDetailsIn,
)
from app.schemas.loan import LoanDetailsCreate, RatePeriodIn
from app.schemas.projection import ScenarioEventIn, ScenarioIn
from app.schemas.recurring import RecurringPlanCreate
from app.services import account_service, projection_service, recurring_service, scenario_service


def _person(db: Session, name: str = "James", dob: date | None = None, retirement_age: int = 67) -> Person:
    person = Person(name=name, date_of_birth=dob, retirement_age=retirement_age)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _isa(db: Session, owner_id: int, value: float = 10000.0):
    return account_service.create_account(
        db,
        AccountCreate(
            name="ISA",
            category=Category.investment,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            expected_return_rate=0.05,
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=value),
        ),
    )


def _cash(db: Session, owner_id: int, value: float = 5000.0):
    return account_service.create_account(
        db,
        AccountCreate(
            name="Savings",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            interest_rate=0.02,
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=value),
        ),
    )


def _db_pension(db: Session, owner_id: int, value: float = 200000.0):
    return account_service.create_account(
        db,
        AccountCreate(
            name="DB Pension",
            category=Category.pension,
            wrapper=Wrapper.db_pension,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            include_in_networth=False,
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=value),
        ),
    )


def _property(db: Session, owner_id: int, value: float = 300000.0):
    return account_service.create_account(
        db,
        AccountCreate(
            name="Home",
            category=Category.property,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.model,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            growth_model=GrowthModelIn(annual_rate=0.03),
            property=PropertyDetailsIn(),
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=value),
        ),
    )


def _mortgage(db: Session, owner_id: int, balance: float = 100000.0):
    return account_service.create_account(
        db,
        AccountCreate(
            name="Mortgage",
            category=Category.mortgage,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.amortising,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=balance),
            loan=LoanDetailsCreate(
                maturity_date=date(2046, 1, 1),
                fallback_rate=0.06,
                rate_periods=[
                    RatePeriodIn(
                        start_date=date(2026, 1, 1),
                        end_date=None,
                        annual_rate=0.045,
                        rate_type=RateType.fixed,
                        label="Fix",
                    )
                ],
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Account kind mapping
# ---------------------------------------------------------------------------


def test_account_kind_mapping(db: Session):
    james = _person(db)
    isa = _isa(db, james.id)
    cash = _cash(db, james.id)
    pension = _db_pension(db, james.id)
    prop = _property(db, james.id)
    mortgage = _mortgage(db, james.id)

    assert projection_service.account_projection_kind(isa) == "growth"
    assert projection_service.account_projection_kind(cash) == "growth"
    assert projection_service.account_projection_kind(pension) == "static"
    assert projection_service.account_projection_kind(prop) == "model"
    assert projection_service.account_projection_kind(mortgage) == "loan"


def test_credit_card_growth_kind_depends_on_interest_rate(db: Session):
    james = _person(db)
    with_rate = account_service.create_account(
        db,
        AccountCreate(
            name="Amex",
            category=Category.credit_card,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            interest_rate=0.22,
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=500.0),
        ),
    )
    without_rate = account_service.create_account(
        db,
        AccountCreate(
            name="Visa",
            category=Category.credit_card,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=500.0),
        ),
    )
    assert projection_service.account_projection_kind(with_rate) == "growth"
    assert projection_service.account_projection_kind(without_rate) == "static"


# ---------------------------------------------------------------------------
# Projection output basics
# ---------------------------------------------------------------------------


def test_projection_totals_grow_over_time(db: Session):
    james = _person(db)
    _isa(db, james.id, 10000.0)

    with freeze_time("2026-09-16"):
        result = projection_service.build_projection(db, months=12)

    assert len(result["dates"]) == 13
    assert result["total"][0] == 10000.0
    assert result["total"][-1] > result["total"][0]


def test_data_version_cache_invalidates_on_balance_write(db: Session):
    james = _person(db)
    account = _isa(db, james.id, 10000.0)

    with freeze_time("2026-09-16"):
        first = projection_service.build_projection(db, months=6)
        assert first["total"][0] == 10000.0

        from app.schemas.balance import BalanceEntryIn
        from app.services import balance_service

        balance_service.upsert_balance(
            db, account, BalanceEntryIn(date=date(2026, 9, 1), balance_gbp=20000.0)
        )

        second = projection_service.build_projection(db, months=6)
        assert second["total"][0] == 20000.0


# ---------------------------------------------------------------------------
# Scenario events: stop_plan / change_plan_amount
# ---------------------------------------------------------------------------


def test_stop_plan_event_ends_contributions_early(db: Session):
    james = _person(db)
    account = _isa(db, james.id, 0.0)
    plan = recurring_service.create_plan(
        db,
        account,
        RecurringPlanCreate(
            account_id=account.id,
            name="Monthly",
            kind=PlanKind.contribution,
            amount_gbp=1000.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 1, 1),
        ),
    )
    scenario = scenario_service.create_scenario(db, ScenarioIn(name="Stop test"))
    scenario_service.create_event(
        db,
        scenario,
        ScenarioEventIn(
            date=date(2027, 1, 1), kind=ScenarioEventKind.stop_plan, plan_id=plan.id, label="Stop plan"
        ),
    )

    with freeze_time("2026-09-16"):
        with_stop = projection_service.build_projection(db, scenario_id=scenario.id, months=24)
        base_scenario = scenario_service.get_default_scenario(db)
        without_stop = projection_service.build_projection(db, scenario_id=base_scenario.id, months=24)

    # After the stop date the plan contributes nothing further, so the scenario total ends up
    # lower than the base scenario where contributions continue.
    assert with_stop["total"][-1] < without_stop["total"][-1]


def test_change_plan_amount_event_changes_future_contributions(db: Session):
    james = _person(db)
    account = _isa(db, james.id, 0.0)
    plan = recurring_service.create_plan(
        db,
        account,
        RecurringPlanCreate(
            account_id=account.id,
            name="Monthly",
            kind=PlanKind.contribution,
            amount_gbp=100.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 1, 1),
        ),
    )
    scenario = scenario_service.create_scenario(db, ScenarioIn(name="Raise"))
    scenario_service.create_event(
        db,
        scenario,
        ScenarioEventIn(
            date=date(2027, 1, 1),
            kind=ScenarioEventKind.change_plan_amount,
            plan_id=plan.id,
            amount_gbp=1000.0,
            label="Pay rise",
        ),
    )

    with freeze_time("2026-09-16"):
        raised = projection_service.build_projection(db, scenario_id=scenario.id, months=18)
        base_scenario = scenario_service.get_default_scenario(db)
        base = projection_service.build_projection(db, scenario_id=base_scenario.id, months=18)

    assert raised["total"][-1] > base["total"][-1]


# ---------------------------------------------------------------------------
# Person scoping
# ---------------------------------------------------------------------------


def test_person_scoping_matches_owner_share(db: Session):
    james = _person(db, "James")
    sam = _person(db, "Sam")
    account_service.create_account(
        db,
        AccountCreate(
            name="Joint savings",
            category=Category.cash,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=0.5), OwnerShareIn(person_id=sam.id, share=0.5)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=10000.0),
        ),
    )

    with freeze_time("2026-09-16"):
        household = projection_service.build_projection(db, months=1)
        james_only = projection_service.build_projection(db, person_id=james.id, months=1)

    assert household["total"][0] == 10000.0
    assert james_only["total"][0] == 5000.0
    assert james_only["by_category"]["cash"][0] == 5000.0


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


def test_networth_target_milestone_date(db: Session):
    james = _person(db)
    _isa(db, james.id, 90000.0)

    with freeze_time("2026-09-16"):
        result = projection_service.build_projection(db, months=60)

    targets = [m for m in result["milestones"] if m["kind"] == "networth_target"]
    assert targets, "expected at least one net worth milestone"
    assert targets[0]["label"] == "£100,000"
    assert targets[0]["date"] > date(2026, 9, 16)


def test_mortgage_free_milestone_matches_schedule(db: Session):
    james = _person(db)
    mortgage = _mortgage(db, james.id, balance=5000.0)

    with freeze_time("2026-09-16"):
        result = projection_service.build_projection(db, months=360)
        from app.services import loan_service

        schedule = loan_service.schedule(db, mortgage)

    mortgage_free = next(m for m in result["milestones"] if m["kind"] == "mortgage_free")
    assert mortgage_free["date"] == schedule["summary"]["payoff_date"]


def test_pension_access_and_retirement_milestones(db: Session):
    james = _person(db, dob=date(1980, 6, 1), retirement_age=65)
    _isa(db, james.id, 1000.0)

    with freeze_time("2026-09-16"):
        result = projection_service.build_projection(db, person_id=james.id, months=600)

    kinds = {m["kind"] for m in result["milestones"]}
    assert "pension_access" in kinds
    assert "retirement" in kinds
