from __future__ import annotations

from datetime import date as _Date

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import BalanceSource, OverpaymentEffect, RateType, RepaymentType


class RatePeriodIn(BaseModel):
    start_date: _Date
    end_date: _Date | None = None
    annual_rate: float
    rate_type: RateType
    label: str | None = None
    payment_override_gbp: float | None = None
    erc_rate: float | None = None


class RatePeriodOut(RatePeriodIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int


class OverpaymentIn(BaseModel):
    date: _Date
    amount_gbp: float = Field(gt=0)
    is_planned: bool = False
    notes: str | None = None


class OverpaymentOut(OverpaymentIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int


class LoanDetailsIn(BaseModel):
    """PUT /accounts/{id}/loan — loan details without rate periods."""

    secured_on_account_id: int | None = None
    lender: str | None = None
    original_amount_gbp: float | None = None
    start_date: _Date | None = None
    maturity_date: _Date
    repayment_type: RepaymentType = RepaymentType.repayment
    payment_day: int = Field(default=1, ge=1, le=28)
    overpayment_effect: OverpaymentEffect = OverpaymentEffect.reduce_term
    overpayment_allowance_rate: float = 0.10
    fallback_rate: float


class LoanDetailsCreate(LoanDetailsIn):
    """Embedded in AccountCreate — includes the initial rate periods."""

    rate_periods: list[RatePeriodIn] = []


class LoanDetailsOut(LoanDetailsIn):
    model_config = ConfigDict(from_attributes=True)

    rate_periods: list[RatePeriodOut] = []


class LoanAnchor(BaseModel):
    date: _Date
    balance_gbp: float
    source: BalanceSource


class CurrentPeriodOut(BaseModel):
    label: str | None
    end_date: _Date | None
    days_left: int | None


class ScheduleBaseline(BaseModel):
    payoff_date: _Date | None
    total_interest_remaining_gbp: float


class LoanScheduleSummary(BaseModel):
    anchor: LoanAnchor
    estimated_balance_today_gbp: float
    current_rate: float
    current_period: CurrentPeriodOut | None
    monthly_payment_gbp: float
    payoff_date: _Date | None
    months_remaining: int
    total_interest_remaining_gbp: float
    baseline: ScheduleBaseline


class ScheduleRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: _Date
    annual_rate: float
    opening_balance: float
    payment: float
    interest: float
    principal: float
    overpayment: float
    closing_balance: float


class AllowanceWarning(BaseModel):
    period_label: str | None
    year_start: _Date
    allowed_gbp: float
    planned_gbp: float


class LoanSchedule(BaseModel):
    summary: LoanScheduleSummary
    rows: list[ScheduleRowOut]
    allowance_warnings: list[AllowanceWarning]


class LumpSumIn(BaseModel):
    date: _Date
    amount_gbp: float = Field(gt=0)


class SimulateIn(BaseModel):
    extra_monthly_gbp: float = 0.0
    lump_sums: list[LumpSumIn] = []
    overpayment_effect: OverpaymentEffect | None = None


class SimulationChartPoint(BaseModel):
    date: _Date
    baseline_balance_gbp: float
    simulated_balance_gbp: float


class LoanSimulation(BaseModel):
    payoff_date: _Date | None
    months_saved: int
    interest_saved_gbp: float
    first_changed_payment_gbp: float | None
    chart: list[SimulationChartPoint]


class EquityLoan(BaseModel):
    account_id: int
    name: str
    owed_gbp: float


class EquityByPerson(BaseModel):
    person_id: int
    equity_gbp: float


class EquityOut(BaseModel):
    value_gbp: float
    loans: list[EquityLoan]
    equity_gbp: float
    ltv: float | None
    by_person: list[EquityByPerson]
