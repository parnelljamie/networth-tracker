from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.projection import (
    CompareIn,
    CompareOut,
    MonteCarloOut,
    ProjectionOut,
    ScenarioEventIn,
    ScenarioEventOut,
    ScenarioIn,
    ScenarioOut,
    ScenarioUpdate,
)
from app.services import projection_service, scenario_service

router = APIRouter(prefix="/api", tags=["projection"])


@router.get("/projection", response_model=ProjectionOut)
def get_projection(
    person_id: int | None = None,
    scenario_id: int | None = None,
    months: int = 360,
    real_terms: bool = False,
    by_account: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    return projection_service.build_projection(
        db, person_id=person_id, scenario_id=scenario_id, months=months, real_terms=real_terms, by_account=by_account
    )


@router.get("/projection/monte-carlo", response_model=MonteCarloOut)
def get_monte_carlo(
    person_id: int | None = None,
    scenario_id: int | None = None,
    months: int = Query(360, ge=1, le=600),
    real_terms: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    return projection_service.build_monte_carlo(
        db, person_id=person_id, scenario_id=scenario_id, months=months, real_terms=real_terms
    )


@router.post("/projection/compare", response_model=CompareOut)
def compare_projection(payload: CompareIn, db: Session = Depends(get_db)) -> dict:
    return projection_service.compare(
        db, payload.scenario_ids, payload.person_id, payload.months, payload.real_terms
    )


@router.get("/scenarios", response_model=list[ScenarioOut])
def list_scenarios(db: Session = Depends(get_db)) -> list:
    return scenario_service.list_scenarios(db)


@router.post("/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(payload: ScenarioIn, db: Session = Depends(get_db)):
    return scenario_service.create_scenario(db, payload)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioOut)
def update_scenario(scenario_id: int, payload: ScenarioUpdate, db: Session = Depends(get_db)):
    scenario = scenario_service.get_scenario(db, scenario_id)
    return scenario_service.update_scenario(db, scenario, payload)


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)) -> None:
    scenario = scenario_service.get_scenario(db, scenario_id)
    scenario_service.delete_scenario(db, scenario)


@router.get("/scenarios/{scenario_id}/events", response_model=list[ScenarioEventOut])
def list_scenario_events(scenario_id: int, db: Session = Depends(get_db)) -> list:
    scenario_service.get_scenario(db, scenario_id)
    return scenario_service.list_events(db, scenario_id)


@router.post("/scenarios/{scenario_id}/events", response_model=ScenarioEventOut, status_code=201)
def create_scenario_event(scenario_id: int, payload: ScenarioEventIn, db: Session = Depends(get_db)):
    scenario = scenario_service.get_scenario(db, scenario_id)
    return scenario_service.create_event(db, scenario, payload)


@router.patch("/scenario-events/{event_id}", response_model=ScenarioEventOut)
def update_scenario_event(event_id: int, payload: ScenarioEventIn, db: Session = Depends(get_db)):
    event = scenario_service.get_event(db, event_id)
    return scenario_service.update_event(db, event, payload)


@router.delete("/scenario-events/{event_id}", status_code=204)
def delete_scenario_event(event_id: int, db: Session = Depends(get_db)) -> None:
    event = scenario_service.get_event(db, event_id)
    scenario_service.delete_event(db, event)
