from datetime import date

import pytest

from app.engine.allowances import AllowanceRules, Contribution, allowance_usage
from app.engine.returns import xirr


# ---------- XIRR ----------
def test_xirr_one_year_ten_percent():
    assert xirr([(date(2025, 1, 1), -1_000), (date(2026, 1, 1), 1_100)]) == pytest.approx(0.10, abs=1e-6)


def test_xirr_two_years_with_leap_day():
    rate = xirr([(date(2024, 1, 1), -1_000), (date(2026, 1, 1), 1_210)])
    assert rate == pytest.approx(1.21 ** (365 / 731) - 1, abs=1e-6)


def test_xirr_monthly_contributions_losing_money_is_negative():
    flows = [(date(2025, m, 1), -500) for m in range(1, 13)] + [(date(2026, 1, 1), 5_700)]
    rate = xirr(flows)
    assert rate is not None and rate < 0


def test_xirr_needs_a_sign_change():
    assert xirr([(date(2025, 1, 1), -1_000), (date(2026, 1, 1), -10)]) is None
    assert xirr([(date(2025, 1, 1), 1_000)]) is None


# ---------- allowances ----------
RULES = AllowanceRules(isa=20_000, lisa=4_000, jisa=9_000, pension_annual=60_000)
ON = date(2026, 9, 15)  # tax year 2026/27


def test_isa_usage_counts_only_this_tax_year_and_personal_subscriptions():
    contributions = [
        Contribution(1, date(2026, 4, 5), 5_000, "isa"),  # previous tax year
        Contribution(1, date(2026, 4, 6), 10_000, "isa"),
        Contribution(1, date(2026, 5, 1), 2_000, "lisa"),
        Contribution(1, date(2026, 5, 2), 500, "lisa", source="government_bonus"),
        Contribution(1, date(2026, 6, 1), 30_000, "isa", source="transfer"),
    ]
    u = allowance_usage(contributions, ON, RULES)[1]
    assert u.tax_year == "2026/27"
    assert u.tax_year_end == date(2027, 4, 5)
    assert u.isa_used == 12_000
    assert u.isa_remaining == 8_000
    assert u.lisa_used == 2_000
    assert u.lisa_remaining == 2_000


def test_lisa_remaining_is_limited_by_overall_isa_allowance():
    u = allowance_usage([Contribution(1, date(2026, 5, 1), 19_000, "isa")], ON, RULES)[1]
    assert u.lisa_remaining == 1_000


def test_pension_usage_is_gross_and_includes_employer_and_relief():
    contributions = [
        Contribution(2, date(2026, 5, 1), 400, "sipp"),
        Contribution(2, date(2026, 5, 1), 100, "sipp", source="tax_relief"),
        Contribution(2, date(2026, 5, 1), 300, "workplace_pension", source="employer"),
        Contribution(2, date(2026, 5, 1), 50_000, "sipp", source="transfer"),
    ]
    u = allowance_usage(contributions, ON, RULES)[2]
    assert u.pension_used == 800
    assert u.pension_remaining == 59_200


def test_jisa_and_zero_rows():
    usage = allowance_usage([Contribution(3, date(2026, 7, 1), 1_500, "jisa")], ON, RULES, person_ids=[1, 3])
    assert usage[3].jisa_used == 1_500
    assert usage[3].jisa_remaining == 7_500
    assert usage[1].isa_used == 0 and usage[1].isa_remaining == 20_000
