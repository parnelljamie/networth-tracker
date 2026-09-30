from __future__ import annotations

from datetime import date as _Date

from pydantic import BaseModel


class AllowanceUsageOut(BaseModel):
    person_id: int
    name: str
    tax_year: str
    tax_year_end: _Date
    days_left: int
    isa_used: float
    isa_limit: float
    isa_remaining: float
    lisa_used: float
    lisa_limit: float
    lisa_remaining: float
    jisa_used: float
    jisa_limit: float
    jisa_remaining: float
    pension_used: float
    pension_limit: float
    pension_remaining: float
    is_estimated: bool
