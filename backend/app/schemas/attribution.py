# `date` imported as `_Date`: see the note in schemas/balance.py — a field literally named `date`
# with a default shadows a same-named type import during Pydantic's lazy annotation evaluation.
from __future__ import annotations

from datetime import date as _Date

from pydantic import BaseModel


class AttributionOut(BaseModel):
    start: _Date
    end: _Date
    person_id: int | None
    start_total_gbp: float
    end_total_gbp: float
    contributions_gbp: float
    market_gbp: float
    mortgage_paid_gbp: float
    revaluation_gbp: float
    other_gbp: float
    total_gbp: float
