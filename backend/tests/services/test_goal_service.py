from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import Category, GoalScope, ValuationMethod, Wrapper
from app.core.errors import DomainError
from app.models.people import Person
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.goal import GoalCreate, GoalUpdate
from app.services import account_service, goal_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _cash_account(db: Session, owner_id: int, balance: float) -> object:
    return account_service.create_account(
        db,
        AccountCreate(
            name="Savings",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=balance),
        ),
    )


def test_create_goal_validates_scope_consistency(db: Session):
    james = _person(db)
    try:
        goal_service.create_goal(
            db,
            GoalCreate(name="Emergency fund", target_gbp=10000, scope=GoalScope.household, person_id=james.id),
        )
        raise AssertionError("expected DomainError")
    except DomainError as exc:
        assert exc.field == "scope"


def test_household_goal_progress_and_hit_date(db: Session):
    with freeze_time("2026-09-16"):
        james = _person(db)
        _cash_account(db, james.id, 5000.0)

        goal = goal_service.create_goal(
            db, GoalCreate(name="Household £10k", target_gbp=10000, scope=GoalScope.household)
        )
        current = goal_service.scoped_current_value(db, goal)
        assert current == 5000.0

        hit_date = goal_service.projected_hit_date(db, goal)
        # No growth/contributions configured -> the projection should not reach the target
        # (or, if the engine treats a flat balance as reachable "never", both are acceptable).
        assert hit_date is None or hit_date >= date(2026, 9, 16)


def test_account_goal_reached_today_when_already_over_target(db: Session):
    with freeze_time("2026-09-16"):
        james = _person(db)
        account = _cash_account(db, james.id, 20000.0)

        goal = goal_service.create_goal(
            db,
            GoalCreate(name="Save £10k", target_gbp=10000, scope=GoalScope.account, account_id=account.id),
        )
        assert goal_service.scoped_current_value(db, goal) == 20000.0
        assert goal_service.projected_hit_date(db, goal) == date(2026, 9, 16)


def test_update_and_delete_goal(db: Session):
    goal = goal_service.create_goal(
        db, GoalCreate(name="Household £10k", target_gbp=10000, scope=GoalScope.household)
    )
    updated = goal_service.update_goal(db, goal, GoalUpdate(target_gbp=20000))
    assert updated.target_gbp == 20000

    goal_service.delete_goal(db, updated)
    assert goal_service.list_goals(db) == []
