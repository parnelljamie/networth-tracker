"""Defined-benefit (DB) pensions, e.g. the Teachers' Pension Scheme (TPS).

A DB pension is a promised yearly income, not a pot. It is described by the pension already
built up (from a benefit statement), how it grows, and when it is paid:

  in service   each year the built-up pension is revalued (CPI + `revaluation_above_cpi`, e.g.
               TPS 2015 career average: CPI + 1.6%) and a new slice is added
               (`accrual_rate` × that year's pensionable salary, e.g. TPS 1/57).
  deferred     after leaving service and before the pension starts, revalued by CPI only.
  in payment   from `pension_start`, increased by CPI each year.

For net worth it is given a capitalised value: yearly pension × `capitalisation_factor` (the
HMRC convention is 20), plus any separate lump sum. Once in payment the remaining value runs
down as the years of payment implied by the factor are used up.

Growth is applied continuously pro-rata over each month rather than in April steps; the
difference is small and keeps values smooth on charts. Pure maths: no DB, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .dates import add_months, years_between

# TPS 2015 (career average) scheme defaults.
TPS_ACCRUAL_RATE = 1 / 57
TPS_REVALUATION_ABOVE_CPI = 0.016
DEFAULT_CAPITALISATION_FACTOR = 20.0


@dataclass(frozen=True)
class DbPensionTerms:
    accrued_annual_pension: float  # yearly pension built up at `accrued_as_of` (statement figure)
    accrued_as_of: date
    pension_start: date  # normal pension date: when the pension is paid in full
    accrual_rate: float = TPS_ACCRUAL_RATE
    revaluation_above_cpi: float = TPS_REVALUATION_ABOVE_CPI
    pensionable_salary: float = 0.0  # yearly, at `accrued_as_of`; 0 once no longer accruing
    salary_growth_rate: float = 0.0
    leave_service: date | None = None  # stops accruing from here (None: accrues until pension_start)
    accrued_lump_sum: float = 0.0  # separate automatic lump sum (older final-salary sections)
    capitalisation_factor: float = DEFAULT_CAPITALISATION_FACTOR


def _accrual_end(terms: DbPensionTerms) -> date:
    if terms.leave_service is None:
        return terms.pension_start
    return min(terms.leave_service, terms.pension_start)


def benefits_on(terms: DbPensionTerms, on: date, cpi: float) -> tuple[float, float]:
    """(yearly pension, lump sum) in nominal £ on `on`. Before `accrued_as_of` the statement
    figures are returned unchanged: nothing earlier is known."""
    pension, lump = terms.accrued_annual_pension, terms.accrued_lump_sum
    if on <= terms.accrued_as_of:
        return pension, lump

    accrual_end = _accrual_end(terms)
    salary = terms.pensionable_salary
    cursor = terms.accrued_as_of
    month = 0
    while cursor < on:
        month += 1
        nxt = min(add_months(terms.accrued_as_of, month), on)
        dt = years_between(cursor, nxt)
        if cursor < accrual_end:
            # Accrue up to the end of service, then treat any remainder of the step as deferred.
            active_end = min(nxt, accrual_end)
            dt_active = years_between(cursor, active_end)
            growth = (1 + cpi + terms.revaluation_above_cpi) ** dt_active
            pension = pension * growth + salary * terms.accrual_rate * dt_active
            lump *= growth
            salary *= (1 + terms.salary_growth_rate) ** dt_active
            dt_rest = dt - dt_active
            if dt_rest > 0:
                pension *= (1 + cpi) ** dt_rest
                lump *= (1 + cpi) ** dt_rest
        elif cursor < terms.pension_start:
            pension *= (1 + cpi) ** dt
            lump *= (1 + cpi) ** dt
        else:
            pension *= (1 + cpi) ** dt  # in payment: CPI increases; the lump sum is already paid
        cursor = nxt
    return pension, lump


def capitalised_value(terms: DbPensionTerms, on: date, cpi: float) -> float:
    """Net-worth value on `on`: pension × factor (+ lump sum) before the pension starts, then
    running down over the remaining years the factor implies."""
    pension, lump = benefits_on(terms, on, cpi)
    if on < terms.pension_start:
        return pension * terms.capitalisation_factor + lump
    years_paid = years_between(terms.pension_start, on)
    return pension * max(terms.capitalisation_factor - years_paid, 0.0)


def pension_at_start(terms: DbPensionTerms, cpi: float) -> tuple[float, float]:
    """(yearly pension, lump sum) in nominal £ when the pension starts."""
    return benefits_on(terms, terms.pension_start, cpi)
