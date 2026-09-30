"""docs/03-domain-logic.md §9 "Goals": progress = scoped current value / target; projected hit
date via `engine.projection.first_date_reaching`."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import Category, GoalScope
from app.core.errors import DomainError, NotFoundError
from app.engine import projection as engine_projection
from app.models.accounts import Account
from app.models.goals import Goal
from app.schemas.goal import GoalCreate, GoalUpdate
from app.services import account_service, networth_service, projection_service, valuation_service

PROGRESS_MAX = 1.0


def _validate_scope(scope: GoalScope, person_id: int | None, account_id: int | None, category: Category | None) -> None:
    """docs §9: scope must match exactly which of person_id/account_id/category is set (mirrors
    recurring_service._validate_kind's style of a single scope-consistency check)."""
    if scope == GoalScope.household:
        if person_id is not None or account_id is not None or category is not None:
            raise DomainError(
                "validation", "Household goals must not set person_id, account_id or category", field="scope"
            )
    elif scope == GoalScope.person:
        if person_id is None:
            raise DomainError("validation", "Person goals require person_id", field="person_id")
        if account_id is not None or category is not None:
            raise DomainError(
                "validation", "Person goals must not set account_id or category", field="scope"
            )
    elif scope == GoalScope.account:
        if account_id is None:
            raise DomainError("validation", "Account goals require account_id", field="account_id")
        if person_id is not None or category is not None:
            raise DomainError(
                "validation", "Account goals must not set person_id or category", field="scope"
            )
    elif scope == GoalScope.category:
        if category is None:
            raise DomainError("validation", "Category goals require category", field="category")
        if person_id is not None or account_id is not None:
            raise DomainError(
                "validation", "Category goals must not set person_id or account_id", field="scope"
            )


def _check_refs_exist(db: Session, person_id: int | None, account_id: int | None) -> None:
    from app.models.people import Person

    if person_id is not None and db.get(Person, person_id) is None:
        raise DomainError("validation", f"Person {person_id} not found", field="person_id")
    if account_id is not None and db.get(Account, account_id) is None:
        raise DomainError("validation", f"Account {account_id} not found", field="account_id")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_goal(db: Session, payload: GoalCreate) -> Goal:
    _validate_scope(payload.scope, payload.person_id, payload.account_id, payload.category)
    _check_refs_exist(db, payload.person_id, payload.account_id)

    goal = Goal(
        name=payload.name,
        target_gbp=round(payload.target_gbp, 2),
        target_date=payload.target_date,
        scope=payload.scope,
        person_id=payload.person_id,
        account_id=payload.account_id,
        category=payload.category,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_goal(db: Session, goal_id: int) -> Goal:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise NotFoundError(f"Goal {goal_id} not found")
    return goal


def list_goals(db: Session) -> list[Goal]:
    return list(db.scalars(select(Goal).order_by(Goal.id)).all())


def update_goal(db: Session, goal: Goal, payload: GoalUpdate) -> Goal:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(goal, field, value)

    _validate_scope(goal.scope, goal.person_id, goal.account_id, goal.category)
    _check_refs_exist(db, goal.person_id, goal.account_id)

    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, goal: Goal) -> None:
    db.delete(goal)
    db.commit()


# ---------------------------------------------------------------------------
# Scoped current value and projected hit date
# ---------------------------------------------------------------------------


def scoped_current_value(db: Session, goal: Goal) -> float:
    """Current value in the goal's scope, per docs §9's decomposition scopes."""
    on = date_today()
    if goal.scope == GoalScope.household:
        return networth_service.get_current(db).total_gbp
    if goal.scope == GoalScope.person:
        return networth_service.get_current(db, person_id=goal.person_id).total_gbp
    if goal.scope == GoalScope.account:
        account = db.get(Account, goal.account_id)
        if account is None:
            return 0.0
        return valuation_service.value_account(db, account, on, live=True).value_gbp
    # category: sum current values of household accounts in that category.
    accounts = account_service.list_accounts(db, category=goal.category, include_archived=False)
    total = 0.0
    for account in accounts:
        if not account.include_in_networth:
            continue
        total += valuation_service.value_account(db, account, on, live=True).value_gbp
    return round(total, 2)


def projected_hit_date(db: Session, goal: Goal) -> date | None:
    """Projected date the goal's scoped value first reaches `target_gbp`.

    Simplification (docs §9 allows this): rather than building a goal-specific projection model,
    this reuses `projection_service.build_projection` — the same engine run and Base-scenario
    assumptions the Projections page uses — and reads off the series for the goal's scope. For
    `account`/`category` scope this means "if this account/category grows under the household's
    current default assumptions", not an isolated projection of that slice alone (Phase 7 spec
    explicitly allows projecting "the correctly-scoped total using the same base-scenario
    assumptions" as a documented simplification).
    """
    on = date_today()
    current = scoped_current_value(db, goal)
    if current >= goal.target_gbp:
        return on

    if goal.scope == GoalScope.household:
        proj = projection_service.build_projection(db, person_id=None)
        series = proj["total"]
        dates = proj["dates"]
    elif goal.scope == GoalScope.person:
        proj = projection_service.build_projection(db, person_id=goal.person_id)
        series = proj["total"]
        dates = proj["dates"]
    elif goal.scope == GoalScope.account:
        proj = projection_service.build_projection(db, person_id=None, by_account=True)
        by_account = proj["by_account"] or {}
        raw = by_account.get(goal.account_id)
        if raw is None:
            return None
        # Loan/liability accounts project as negative series; goals are framed as positive
        # targets (e.g. "pay off the mortgage"), so compare on magnitude.
        series = [abs(x) for x in raw]
        dates = proj["dates"]
    else:  # category
        proj = projection_service.build_projection(db, person_id=None, by_account=True)
        series = proj["by_category"].get(goal.category.value)
        if series is None:
            return None
        dates = proj["dates"]

    return engine_projection.first_date_reaching(dates, series, goal.target_gbp)
