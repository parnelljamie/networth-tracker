from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DepositProtectionEntry(BaseModel):
    provider: str
    person_id: int
    person_name: str
    total_gbp: float
    limit_gbp: float
    exceeded: bool


class DepositProtectionOut(BaseModel):
    entries: list[DepositProtectionEntry]


class XirrOut(BaseModel):
    xirr: float | None
    # False when there's under a year of history: `xirr` is then the return since `since`.
    annualised: bool = True
    since: date | None = None
