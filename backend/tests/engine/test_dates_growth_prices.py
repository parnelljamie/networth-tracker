from datetime import date

import pytest

from app.engine.dates import (
    add_months,
    months_between,
    projection_dates,
    tax_year_end,
    tax_year_label,
    tax_year_start,
    whole_years_between,
)
from app.engine.growth import deflate, grow_value, growth_factor, monthly_rate, value_on
from app.engine.prices import MissingFxRate, fix_pence_glitch, fx_symbol, major_currency, to_gbp


# ---------- dates ----------
def test_add_months_clamps_day():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)


def test_months_between_ignores_days():
    assert months_between(date(2026, 1, 15), date(2026, 3, 1)) == 2
    assert months_between(date(2026, 2, 1), date(2051, 1, 1)) == 299


def test_uk_tax_year_boundaries():
    assert tax_year_label(date(2026, 4, 5)) == "2025/26"
    assert tax_year_label(date(2026, 4, 6)) == "2026/27"
    assert tax_year_start(date(2026, 9, 15)) == date(2026, 4, 6)
    assert tax_year_end(date(2026, 9, 15)) == date(2027, 4, 5)
    assert tax_year_label(date(2099, 12, 1)) == "2099/00"


def test_whole_years_between():
    assert whole_years_between(date(2026, 1, 1), date(2026, 12, 31)) == 0
    assert whole_years_between(date(2026, 1, 1), date(2027, 1, 1)) == 1
    assert whole_years_between(date(2024, 2, 29), date(2025, 2, 28)) == 0
    assert whole_years_between(date(2026, 1, 1), date(2025, 1, 1)) == 0


def test_projection_dates_are_month_ends_after_today():
    assert projection_dates(date(2026, 9, 15), 2) == [
        date(2026, 9, 15),
        date(2026, 10, 31),
        date(2026, 11, 30),
    ]


# ---------- growth ----------
def test_compound_and_linear_growth():
    assert grow_value(10_000, 0.05, 2) == pytest.approx(11_025)
    assert grow_value(10_000, 0.05, 2, method="linear") == pytest.approx(11_000)
    assert grow_value(20_000, -0.15, 3) == pytest.approx(12_282.5)
    assert grow_value(10_000, -0.6, 2, method="linear") == 0


def test_floor_and_cap_only_act_in_their_direction():
    assert grow_value(20_000, -0.15, 10, floor=5_000) == 5_000
    assert grow_value(1_000, 0.10, 10, cap=1_500) == 1_500
    assert grow_value(1_000, -0.10, 1, cap=1_500) == pytest.approx(900)


def test_floor_never_lifts_a_value_observed_below_it():
    assert grow_value(4_000, -0.15, 1, floor=5_000) == 4_000


def test_growth_edge_cases():
    assert growth_factor(0.05, -1) == 1.0
    assert growth_factor(-1.5, 2) == 0.0
    assert monthly_rate(0.12) == pytest.approx(0.0094888, abs=1e-6)
    assert deflate(10_000 * 1.025**10, 0.025, 10) == pytest.approx(10_000)
    assert value_on(100, date(2026, 1, 1), date(2025, 1, 1), 0.1) == 100


# ---------- prices ----------
def test_pence_are_converted_to_pounds():
    assert to_gbp(7_250.0, "GBp") == pytest.approx(72.50)
    assert to_gbp(7_250.0, "GBX") == pytest.approx(72.50)
    assert to_gbp(72.50, "GBP") == pytest.approx(72.50)
    assert major_currency("GBp") == ("GBP", 0.01)
    assert major_currency("usd") == ("USD", 1.0)


def test_foreign_prices_use_fx():
    assert to_gbp(100.0, "USD", {"USD": 0.75}) == pytest.approx(75.0)
    assert fx_symbol("USD") == "USDGBP=X"
    with pytest.raises(MissingFxRate):
        to_gbp(100.0, "EUR", {"USD": 0.75})


def test_hundred_x_glitch_guard():
    assert fix_pence_glitch(7_250.0, 72.40) == (pytest.approx(72.50), True)
    assert fix_pence_glitch(0.7245, 72.40) == (pytest.approx(72.45), True)
    assert fix_pence_glitch(73.10, 72.40) == (73.10, False)
    assert fix_pence_glitch(73.10, None) == (73.10, False)
