# `date` imported as `_Date`: see the note in schemas/balance.py — a field literally named `date`
# with a default shadows a same-named type import during Pydantic's lazy annotation evaluation.
from __future__ import annotations

from datetime import date as _Date

from pydantic import BaseModel, ConfigDict

from app.core.enums import ScenarioEventKind


class ScenarioIn(BaseModel):
    name: str
    return_adjustment: float = 0.0
    inflation_rate: float | None = None
    property_growth_rate: float | None = None
    notes: str | None = None


class ScenarioUpdate(BaseModel):
    name: str | None = None
    return_adjustment: float | None = None
    inflation_rate: float | None = None
    property_growth_rate: float | None = None
    notes: str | None = None


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_default: bool
    return_adjustment: float
    inflation_rate: float | None
    property_growth_rate: float | None
    notes: str | None


class ScenarioEventIn(BaseModel):
    date: _Date
    kind: ScenarioEventKind
    account_id: int | None = None
    plan_id: int | None = None
    amount_gbp: float | None = None
    rate: float | None = None
    label: str


class ScenarioEventOut(ScenarioEventIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int


class MilestoneOut(BaseModel):
    kind: str
    label: str
    date: _Date
    person_id: int | None = None


class AssumptionsOut(BaseModel):
    inflation_rate: float
    return_adjustment: float
    real_terms: bool


class ProjectionOut(BaseModel):
    dates: list[_Date]
    total: list[float]
    by_category: dict[str, list[float]]
    by_person: dict[int, list[float]]
    by_account: dict[int, list[float]] | None = None
    contributions: list[float]
    milestones: list[MilestoneOut]
    assumptions: AssumptionsOut


class CompareIn(BaseModel):
    scenario_ids: list[int]
    person_id: int | None = None
    months: int = 360
    real_terms: bool = False


class CompareSeries(BaseModel):
    scenario_id: int
    name: str
    total: list[float]


class CompareOut(BaseModel):
    dates: list[_Date]
    series: list[CompareSeries]


class MonteCarloOut(BaseModel):
    """Percentiles of the projected total at each date; `deterministic` is the plain projection."""

    dates: list[_Date]
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]
    deterministic: list[float]
    paths: int
