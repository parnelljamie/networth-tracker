from datetime import date

import pytest

from app.engine.amortisation import LoanTerms, build_schedule
from app.engine.growth import grow_value
from app.engine.projection import (
    Assumptions,
    LumpSum,
    ProjectionAccount,
    ProjectionFlow,
    RateChange,
    first_date_reaching,
    project,
)
from app.engine.recurring import Plan

MORTGAGE_TERMS = LoanTerms(maturity=date(2051, 1, 1), fallback_rate=0.045)


def test_growth_compounds_over_actual_days():
    acct = ProjectionAccount(1, "investment", "growth", 10_000, owners={1: 1.0}, annual_rate=0.05)
    r = project([acct], [], [], date(2026, 1, 31), 12)
    assert r.dates[12] == date(2027, 1, 31)
    assert r.by_account[1][12] == pytest.approx(10_000 * 1.05 ** (365 / 365.25), abs=0.01)
    assert r.total == r.by_account[1]
    assert r.by_person[1] == r.by_account[1]


def test_fees_and_scenario_return_adjustment():
    acct = ProjectionAccount(1, "pension", "growth", 10_000, annual_rate=0.05, annual_fee_rate=0.01)
    years = (date(2027, 1, 31) - date(2026, 1, 1)).days / 365.25
    base = project([acct], [], [], date(2026, 1, 1), 12)
    better = project([acct], [], [], date(2026, 1, 1), 12, Assumptions(return_adjustment=0.02))
    assert base.by_account[1][12] == pytest.approx(10_000 * 1.04**years, abs=0.01)
    assert better.by_account[1][12] == pytest.approx(10_000 * 1.06**years, abs=0.01)

    cash = ProjectionAccount(2, "cash", "growth", 10_000, annual_rate=0.04, scenario_adjustable=False)
    shifted = project([cash], [], [], date(2026, 1, 1), 12, Assumptions(return_adjustment=0.02))
    assert shifted.by_account[2][12] == pytest.approx(10_000 * 1.04**years, abs=0.01)


def test_contributions_after_today_include_tax_relief():
    plan = Plan(80, "monthly", date(2026, 1, 1), tax_relief_rate=0.25)
    acct = ProjectionAccount(1, "pension", "growth", 0, owners={1: 1.0})
    r = project([acct], [ProjectionFlow(1, plan)], [], date(2026, 1, 1), 12)
    assert r.by_account[1][1] == 100  # 1 Feb only: 1 Jan is today, already inside today's value
    assert r.by_account[1][12] == 1_200  # 1 Feb 2026 .. 1 Jan 2027
    assert r.contributions[12] == 1_200


def test_withdrawals_and_lump_sums_never_push_assets_negative():
    acct = ProjectionAccount(1, "cash", "growth", 1_000)
    withdraw = ProjectionFlow(1, Plan(400, "monthly", date(2026, 2, 1)), kind="withdrawal")
    r = project([acct], [withdraw], [LumpSum(1, date(2026, 3, 15), 250)], date(2026, 1, 15), 4)
    assert r.by_account[1] == [1_000, 600, 450, 50, 0]


def test_loan_follows_amortisation_schedule_and_counts_negative():
    acct = ProjectionAccount(7, "mortgage", "loan", 200_000, owners={1: 0.5, 2: 0.5}, loan_terms=MORTGAGE_TERMS)
    r = project([acct], [], [], date(2026, 1, 1), 12)
    rows = build_schedule(MORTGAGE_TERMS, 200_000, date(2026, 1, 1))
    assert r.by_account[7][12] == -rows[11].closing_balance  # after the 1 Jan 2027 payment
    assert r.by_category["mortgage"][0] == -200_000
    assert r.by_person[1][12] == pytest.approx(r.by_account[7][12] / 2, abs=0.01)
    assert len(r.loan_schedules[7]) == 12


def test_overpayment_plan_reduces_loan_balance():
    acct = ProjectionAccount(7, "mortgage", "loan", 200_000, loan_terms=MORTGAGE_TERMS)
    overpay = ProjectionFlow(7, Plan(200, "monthly", date(2026, 2, 1)), kind="overpayment")
    base = project([acct], [], [], date(2026, 1, 1), 24)
    over = project([acct], [overpay], [], date(2026, 1, 1), 24)
    assert over.by_account[7][24] > base.by_account[7][24] + 24 * 200


def test_model_assets_people_and_real_terms():
    car = ProjectionAccount(3, "other_asset", "model", 20_000, owners={2: 1.0}, annual_rate=-0.15, floor=2_000)
    house = ProjectionAccount(4, "property", "model", 400_000, owners={1: 0.5, 2: 0.5}, annual_rate=0.03)
    r = project([car, house], [], [], date(2026, 1, 31), 36, Assumptions(inflation_rate=0.03, real_terms=True))
    years = (r.dates[36] - date(2026, 1, 31)).days / 365.25
    assert r.by_account[3][36] == pytest.approx(grow_value(20_000, -0.15, years) / 1.03**years, abs=0.01)
    assert r.by_account[4][36] == pytest.approx(400_000, abs=0.01)  # growth equals inflation
    assert r.by_person[2][36] == pytest.approx(r.by_account[3][36] + r.by_account[4][36] / 2, abs=0.02)


def test_rate_change_and_milestones():
    acct = ProjectionAccount(1, "pension", "growth", 100_000, annual_rate=0.06)
    r = project([acct], [], [], date(2026, 1, 1), 24)
    assert first_date_reaching(r.dates, r.total, 105_000) == date(2026, 11, 30)
    assert first_date_reaching(r.dates, r.total, 1_000_000) is None

    derisked = project([acct], [], [], date(2026, 1, 1), 24, rate_changes=[RateChange(1, date(2026, 12, 31), 0.0)])
    assert derisked.by_account[1][11] > 100_000
    assert derisked.by_account[1][24] == derisked.by_account[1][11]


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        project([ProjectionAccount(1, "mortgage", "loan", 1_000)], [], [], date(2026, 1, 1), 1)
    with pytest.raises(ValueError):
        project([ProjectionAccount(1, "cash", "magic", 1_000)], [], [], date(2026, 1, 1), 1)
