# `date` imported as `_Date`: see the note in schemas/balance.py — a field literally named `date`
# with a default shadows a same-named type import during Pydantic's lazy annotation evaluation.
from __future__ import annotations

from datetime import date as _Date

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Category, GoalScope


class GoalCreate(BaseModel):
    name: str
    target_gbp: float = Field(gt=0)
    target_date: _Date | None = None
    scope: GoalScope
    person_id: int | None = None
    account_id: int | None = None
    category: Category | None = None


class GoalUpdate(BaseModel):
    name: str | None = None
    target_gbp: float | None = Field(default=None, gt=0)
    target_date: _Date | None = None
    scope: GoalScope | None = None
    person_id: int | None = None
    account_id: int | None = None
    category: Category | None = None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_gbp: float
    target_date: _Date | None
    scope: GoalScope
    person_id: int | None
    account_id: int | None
    category: Category | None
    current_value_gbp: float = 0.0
    progress: float = 0.0
    projected_hit_date: _Date | None = None
