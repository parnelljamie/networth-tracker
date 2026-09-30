from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.account import AccountSummary


class ChangeFigure(BaseModel):
    abs_gbp: float | None
    pct: float | None


class NetWorthChanges(BaseModel):
    day: ChangeFigure
    week: ChangeFigure
    month: ChangeFigure
    ytd: ChangeFigure
    year: ChangeFigure


class CategoryShare(BaseModel):
    category: str
    value_gbp: float
    share_of_assets: float


class PersonShare(BaseModel):
    person_id: int
    name: str
    color: str | None
    value_gbp: float


class StaleAccount(BaseModel):
    account_id: int
    name: str
    days_since: int
    staleness: str


class Freshness(BaseModel):
    prices_updated_at: datetime | None
    stale_accounts: list[StaleAccount]


class NetWorthCurrent(BaseModel):
    as_of: datetime
    person_id: int | None
    total_gbp: float
    assets_gbp: float
    liabilities_gbp: float
    liquid_gbp: float
    illiquid_gbp: float
    changes: NetWorthChanges
    by_category: list[CategoryShare]
    by_person: list[PersonShare]
    by_asset_class: list[dict[str, Any]] = []
    accounts: list[AccountSummary]
    top_movers: list[dict[str, Any]] = []
    freshness: Freshness
    pending_transactions: int = 0


class HistorySeriesOut(BaseModel):
    key: str
    label: str
    values: list[float]


class NetWorthHistory(BaseModel):
    dates: list[date]
    total: list[float]
    series: list[HistorySeriesOut]


class AccountHistoryPoint(BaseModel):
    date: date
    value_gbp: float
    cost_basis_gbp: float | None
    net_contributions_gbp: float | None
    is_estimated: bool


class RebuildRequest(BaseModel):
    account_id: int | None = None
    from_date: date


class RebuildJobId(BaseModel):
    job_id: str


class JobStatusOut(BaseModel):
    status: str
    progress: float
    error: str | None = None


class BackupOut(BaseModel):
    path: str
    copied_to: str | None = None
    copy_error: str | None = None


class BackupInfoOut(BaseModel):
    filename: str
    size_bytes: int
    created_at: str
