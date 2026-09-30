"""Scenario and scenario-event CRUD. docs/02-data-model.md "scenarios", "scenario_events"."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ScenarioEventKind
from app.core.errors import DomainError, NotFoundError
from app.models.scenarios import Scenario, ScenarioEvent
from app.schemas.projection import ScenarioEventIn, ScenarioIn, ScenarioUpdate

# docs/BUILD_PLAN.md Phase 6: seed Base (default), Optimistic (+2%), Pessimistic (-2%).
DEFAULT_SCENARIOS: list[dict] = [
    {"name": "Base", "is_default": True, "return_adjustment": 0.0},
    {"name": "Optimistic", "is_default": False, "return_adjustment": 0.02},
    {"name": "Pessimistic", "is_default": False, "return_adjustment": -0.02},
]


def _bump() -> None:
    from app.services import projection_service

    projection_service.bump_data_version()


def ensure_defaults(db: Session) -> None:
    existing = set(db.scalars(select(Scenario.name)).all())
    changed = False
    for row in DEFAULT_SCENARIOS:
        if row["name"] not in existing:
            db.add(Scenario(**row))
            changed = True
    if changed:
        db.commit()
        _bump()


def list_scenarios(db: Session) -> list[Scenario]:
    return list(db.scalars(select(Scenario).order_by(Scenario.id)).all())


def get_scenario(db: Session, scenario_id: int) -> Scenario:
    row = db.get(Scenario, scenario_id)
    if row is None:
        raise NotFoundError(f"Scenario {scenario_id} not found")
    return row


def get_default_scenario(db: Session) -> Scenario:
    row = db.scalars(select(Scenario).where(Scenario.is_default.is_(True))).first()
    if row is None:
        row = db.scalars(select(Scenario).order_by(Scenario.id)).first()
    if row is None:
        raise NotFoundError("No scenarios configured")
    return row


def create_scenario(db: Session, payload: ScenarioIn) -> Scenario:
    row = Scenario(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    _bump()
    return row


def update_scenario(db: Session, scenario: Scenario, payload: ScenarioUpdate) -> Scenario:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scenario, field, value)
    db.commit()
    db.refresh(scenario)
    _bump()
    return scenario


def delete_scenario(db: Session, scenario: Scenario) -> None:
    if scenario.is_default:
        raise DomainError("validation", "Cannot delete the default scenario", field=None)
    db.delete(scenario)
    db.commit()
    _bump()


def _validate_event(payload: ScenarioEventIn) -> None:
    if payload.kind in (ScenarioEventKind.lump_sum, ScenarioEventKind.set_return_rate) and payload.account_id is None:
        raise DomainError(
            "validation", f"{payload.kind.value} events require an account_id", field="account_id"
        )
    if (
        payload.kind in (ScenarioEventKind.stop_plan, ScenarioEventKind.change_plan_amount)
        and payload.plan_id is None
    ):
        raise DomainError(
            "validation", f"{payload.kind.value} events require a plan_id", field="plan_id"
        )
    if (
        payload.kind in (ScenarioEventKind.lump_sum, ScenarioEventKind.change_plan_amount)
        and payload.amount_gbp is None
    ):
        raise DomainError(
            "validation", f"{payload.kind.value} events require amount_gbp", field="amount_gbp"
        )
    if payload.kind == ScenarioEventKind.set_return_rate and payload.rate is None:
        raise DomainError("validation", "set_return_rate events require rate", field="rate")


def list_events(db: Session, scenario_id: int) -> list[ScenarioEvent]:
    return list(
        db.scalars(
            select(ScenarioEvent)
            .where(ScenarioEvent.scenario_id == scenario_id)
            .order_by(ScenarioEvent.date)
        ).all()
    )


def create_event(db: Session, scenario: Scenario, payload: ScenarioEventIn) -> ScenarioEvent:
    _validate_event(payload)
    row = ScenarioEvent(scenario_id=scenario.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    _bump()
    return row


def get_event(db: Session, event_id: int) -> ScenarioEvent:
    row = db.get(ScenarioEvent, event_id)
    if row is None:
        raise NotFoundError(f"Scenario event {event_id} not found")
    return row


def update_event(db: Session, event: ScenarioEvent, payload: ScenarioEventIn) -> ScenarioEvent:
    _validate_event(payload)
    for field, value in payload.model_dump().items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    _bump()
    return event


def delete_event(db: Session, event: ScenarioEvent) -> None:
    db.delete(event)
    db.commit()
    _bump()
