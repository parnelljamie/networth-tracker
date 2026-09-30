from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import BalanceSource, Category, GrowthMethod, ValuationMethod, Wrapper
from app.schemas.db_pension import DbPensionDetailsIn, DbPensionDetailsOut, DbPensionSummaryOut
from app.schemas.loan import LoanDetailsCreate, LoanDetailsOut


class OwnerShareIn(BaseModel):
    person_id: int
    share: float = Field(gt=0, le=1)


class OwnerShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    person_id: int
    name: str
    color: str | None
    share: float


class GrowthModelIn(BaseModel):
    annual_rate: float
    method: GrowthMethod = GrowthMethod.compound
    floor_value_gbp: float | None = None
    cap_value_gbp: float | None = None


class GrowthModelOut(GrowthModelIn):
    model_config = ConfigDict(from_attributes=True)


class PropertyDetailsIn(BaseModel):
    address: str | None = None
    purchase_date: date | None = None
    purchase_price_gbp: float | None = None
    is_main_residence: bool = True


class PropertyDetailsOut(PropertyDetailsIn):
    model_config = ConfigDict(from_attributes=True)


class InitialBalanceIn(BaseModel):
    date: date
    balance_gbp: float = Field(ge=0)
    source: BalanceSource = BalanceSource.manual


class AccountCreate(BaseModel):
    name: str
    category: Category
    wrapper: Wrapper = Wrapper.none
    valuation_method: ValuationMethod
    provider: str | None = None
    owners: list[OwnerShareIn]
    include_in_networth: bool | None = None
    is_liquid: bool | None = None
    expected_return_rate: float | None = None
    annual_fee_rate: float = 0.0
    interest_rate: float | None = None
    opened_date: date | None = None
    notes: str | None = None
    initial_balance: InitialBalanceIn | None = None
    growth_model: GrowthModelIn | None = None
    property: PropertyDetailsIn | None = None
    loan: LoanDetailsCreate | None = None
    db_pension: DbPensionDetailsIn | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    owners: list[OwnerShareIn] | None = None
    include_in_networth: bool | None = None
    is_liquid: bool | None = None
    expected_return_rate: float | None = None
    annual_fee_rate: float | None = None
    interest_rate: float | None = None
    opened_date: date | None = None
    closed_date: date | None = None
    notes: str | None = None


class AccountSummary(BaseModel):
    id: int
    name: str
    category: Category
    wrapper: Wrapper
    valuation_method: ValuationMethod
    provider: str | None
    owners: list[OwnerShareOut]
    value_gbp: float
    scoped_value_gbp: float
    cost_basis_gbp: float | None = None
    gain_gbp: float | None = None
    gain_pct: float | None = None
    day_change_gbp: float | None = None
    day_change_pct: float | None = None
    is_liability: bool
    is_liquid: bool
    include_in_networth: bool
    is_estimated: bool
    is_archived: bool
    last_updated: datetime | None
    staleness: str
    # Balance/model/amortising: days since the last entry. Holdings: age of the oldest held
    # price. None when there is nothing to count from (no entry, or nothing priced yet).
    days_since_update: int | None = None
    detail: str | None = None


class AccountDetail(AccountSummary):
    expected_return_rate: float | None = None
    annual_fee_rate: float
    interest_rate: float | None = None
    opened_date: date | None = None
    closed_date: date | None = None
    notes: str | None = None
    growth_model: GrowthModelOut | None = None
    property: PropertyDetailsOut | None = None
    loan: LoanDetailsOut | None = None
    db_pension: DbPensionDetailsOut | None = None
    db_pension_summary: DbPensionSummaryOut | None = None
    # "trading212" when transactions sync from a broker's API (services/trading212_service.py).
    broker_sync: str | None = None
