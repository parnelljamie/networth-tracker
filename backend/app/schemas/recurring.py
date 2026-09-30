# `date` imported as `_Date`: see the note in schemas/balance.py — a field literally named `date`
# with a default shadows a same-named type import during Pydantic's lazy annotation evaluation.
from __future__ import annotations

from datetime import date as _Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ContributionSource, Frequency, PlanKind


class PlanAllocationIn(BaseModel):
    instrument_id: int
    weight: float = Field(gt=0, le=1)


class PlanAllocationOut(PlanAllocationIn):
    model_config = ConfigDict(from_attributes=True)


class RecurringPlanCreate(BaseModel):
    account_id: int
    name: str
    kind: PlanKind
    amount_gbp: float = Field(gt=0)
    frequency: Frequency
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    start_date: _Date
    end_date: _Date | None = None
    annual_increase_rate: float = 0.0
    contribution_source: ContributionSource = ContributionSource.personal
    tax_relief_rate: float = 0.0
    auto_record: bool = False
    is_active: bool = True
    allocations: list[PlanAllocationIn] = []


class RecurringPlanUpdate(BaseModel):
    name: str | None = None
    amount_gbp: float | None = None
    frequency: Frequency | None = None
    day_of_month: int | None = None
    start_date: _Date | None = None
    end_date: _Date | None = None
    annual_increase_rate: float | None = None
    contribution_source: ContributionSource | None = None
    tax_relief_rate: float | None = None
    auto_record: bool | None = None
    is_active: bool | None = None
    allocations: list[PlanAllocationIn] | None = None


class RecurringPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    name: str
    kind: PlanKind
    amount_gbp: float
    frequency: Frequency
    day_of_month: int | None
    start_date: _Date
    end_date: _Date | None
    annual_increase_rate: float
    contribution_source: ContributionSource
    tax_relief_rate: float
    auto_record: bool
    last_recorded_date: _Date | None
    is_active: bool
    allocations: list[PlanAllocationOut] = []
    next_date: _Date | None = None


class UpcomingItem(BaseModel):
    date: _Date
    # None for a loan's scheduled payment, which comes from the loan terms, not a plan.
    plan_id: int | None
    account_id: int
    name: str
    kind: PlanKind | Literal["loan_payment"]
    amount_gbp: float
    gross_amount_gbp: float
