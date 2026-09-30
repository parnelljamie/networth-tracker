from __future__ import annotations

# Imported as `_Date`, not `date`: a model field literally named `date` with a default value
# (e.g. BalanceEntryUpdate below) creates a class attribute that shadows a same-named type import
# during Pydantic's lazy (string) annotation evaluation, breaking `date | None` at class-creation time.
from datetime import date as _Date

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import BalanceSource


class BalanceEntryIn(BaseModel):
    date: _Date
    balance_gbp: float = Field(ge=0)
    source: BalanceSource = BalanceSource.manual
    notes: str | None = None


class BalanceEntryUpdate(BaseModel):
    date: _Date | None = None
    balance_gbp: float | None = Field(default=None, ge=0)
    source: BalanceSource | None = None
    notes: str | None = None


class BalanceEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    date: _Date
    balance_gbp: float
    source: BalanceSource
    notes: str | None


class QuickUpdateRow(BaseModel):
    account_id: int
    name: str
    category: str
    owners: list[str]
    valuation_method: str
    last_date: _Date | None
    last_balance_gbp: float | None
    modelled_value_gbp: float | None
    days_since: int | None
    staleness: str


class BulkBalanceEntry(BaseModel):
    account_id: int
    date: _Date
    balance_gbp: float = Field(ge=0)
    source: BalanceSource = BalanceSource.manual


class BulkBalancesIn(BaseModel):
    entries: list[BulkBalanceEntry]


class BulkBalancesOut(BaseModel):
    saved: int
