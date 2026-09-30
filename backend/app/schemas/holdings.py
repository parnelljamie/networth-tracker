from __future__ import annotations

from datetime import date as _Date
from datetime import datetime

from pydantic import BaseModel

from app.schemas.instrument import InstrumentOut


class HoldingPosition(BaseModel):
    instrument: InstrumentOut
    units: float
    avg_cost_gbp: float
    cost_basis_gbp: float
    price_gbp: float
    price_at: datetime | None
    is_stale: bool
    value_gbp: float
    gain_gbp: float
    gain_pct: float | None
    day_change_gbp: float
    day_change_pct: float | None
    weight: float


class HoldingsTotals(BaseModel):
    value_gbp: float
    cost_basis_gbp: float
    gain_gbp: float
    gain_pct: float | None
    day_change_gbp: float
    day_change_pct: float | None


class Holdings(BaseModel):
    account_id: int
    as_of: datetime
    cash_gbp: float
    positions: list[HoldingPosition]
    totals: HoldingsTotals
    warnings: list[str] = []


class SetHoldingIn(BaseModel):
    units: float
    avg_cost_gbp: float
    as_of: _Date | None = None


class SetCashIn(BaseModel):
    cash_gbp: float
    as_of: _Date | None = None
