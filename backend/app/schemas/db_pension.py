from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DbPensionDetailsIn(BaseModel):
    scheme: str = "tps_2015"  # "tps_2015" (preset) or "custom"
    accrued_annual_pension_gbp: float = Field(ge=0)
    accrued_lump_sum_gbp: float = Field(default=0.0, ge=0)
    accrued_as_of: date
    accrual_rate: float = Field(gt=0, le=1)
    revaluation_above_cpi: float = 0.0
    pensionable_salary_gbp: float = Field(default=0.0, ge=0)
    salary_growth_rate: float = 0.0
    normal_pension_age: int = Field(ge=50, le=75)
    is_active_member: bool = True
    capitalisation_factor: float = Field(default=20.0, gt=0, le=40)


class DbPensionDetailsOut(DbPensionDetailsIn):
    model_config = ConfigDict(from_attributes=True)


class DbPensionSummaryOut(BaseModel):
    """Derived figures for display. Money is nominal unless the name says `_today_money`."""

    annual_pension_today_gbp: float
    lump_sum_today_gbp: float
    capitalised_value_gbp: float
    pension_start_date: date | None  # None when the owner has no date of birth
    annual_pension_at_start_gbp: float | None
    annual_pension_at_start_today_money_gbp: float | None
    lump_sum_at_start_gbp: float | None
