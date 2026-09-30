from __future__ import annotations

from datetime import date

import pytest

from app.engine.db_pension import (
    DbPensionTerms,
    benefits_on,
    capitalised_value,
    pension_at_start,
)

CPI = 0.025


def _tps(**overrides) -> DbPensionTerms:
    base = dict(
        accrued_annual_pension=5000.0,
        accrued_as_of=date(2026, 3, 31),
        pension_start=date(2062, 3, 10),
        pensionable_salary=0.0,
    )
    base.update(overrides)
    return DbPensionTerms(**base)


def test_statement_figure_is_returned_on_and_before_its_date():
    terms = _tps()
    assert benefits_on(terms, date(2026, 3, 31), CPI) == (5000.0, 0.0)
    assert benefits_on(terms, date(2025, 1, 1), CPI) == (5000.0, 0.0)


def test_in_service_revaluation_is_cpi_plus_1_6_pct_a_year():
    terms = _tps()
    pension, _ = benefits_on(terms, date(2027, 3, 31), CPI)
    assert pension == pytest.approx(5000.0 * 1.041, rel=1e-3)  # actual/365.25 year basis


def test_a_year_of_service_adds_one_57th_of_salary():
    # No revaluation, flat salary: a year adds exactly salary / 57.
    terms = _tps(pensionable_salary=57_000.0, revaluation_above_cpi=0.0)
    pension, _ = benefits_on(terms, date(2027, 3, 31), 0.0)
    assert pension == pytest.approx(5000.0 + 1000.0, rel=1e-3)  # actual/365.25 year basis


def test_after_leaving_service_it_only_keeps_pace_with_cpi():
    terms = _tps(pensionable_salary=57_000.0, leave_service=date(2026, 3, 31))
    pension, _ = benefits_on(terms, date(2027, 3, 31), CPI)
    assert pension == pytest.approx(5000.0 * 1.025, rel=1e-3)  # actual/365.25 year basis


def test_capitalised_value_is_pension_times_factor_plus_lump_sum():
    terms = _tps(accrued_lump_sum=15_000.0)
    assert capitalised_value(terms, date(2026, 3, 31), CPI) == pytest.approx(5000.0 * 20 + 15_000.0)


def test_capitalised_value_runs_down_once_in_payment():
    terms = _tps(accrued_as_of=date(2026, 1, 1), pension_start=date(2026, 1, 1))
    ten_years_in = date(2036, 1, 1)
    pension, _ = benefits_on(terms, ten_years_in, CPI)
    assert capitalised_value(terms, ten_years_in, CPI) == pytest.approx(pension * 10, rel=1e-3)
    assert capitalised_value(terms, date(2047, 1, 1), CPI) == 0.0


def test_pension_at_start_includes_growth_and_new_accrual():
    terms = _tps(pensionable_salary=40_000.0, salary_growth_rate=0.03)
    pension, _ = pension_at_start(terms, CPI)
    assert pension > 5000.0 * 1.041**37  # revaluation alone, before any new slices
