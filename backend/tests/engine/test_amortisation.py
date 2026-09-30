from datetime import date

import pytest

from app.engine.amortisation import (
    LoanTerms,
    RatePeriod,
    annuity_payment,
    balance_on,
    build_schedule,
    payments_to_clear,
    summarise,
)

START = date(2026, 1, 1)
MATURITY = date(2051, 1, 1)  # payments 1 Feb 2026 .. 1 Jan 2051 = 300
FIX = (RatePeriod(start=START, end=date(2028, 1, 31), annual_rate=0.045),)


def terms(**overrides) -> LoanTerms:
    return LoanTerms(**{"maturity": MATURITY, "fallback_rate": 0.045, **overrides})


def test_annuity_payment_matches_published_calculators():
    # £200,000 over 25 years at 4.5% is £1,111.66 a month
    assert annuity_payment(200_000, 0.045, 300) == pytest.approx(1111.66, abs=0.01)
    assert annuity_payment(12_000, 0.0, 12) == 1_000
    assert annuity_payment(0, 0.05, 12) == 0


def test_level_repayment_schedule():
    rows = build_schedule(terms(), 200_000, START)
    assert len(rows) == 300
    assert rows[0].date == date(2026, 2, 1)
    assert rows[0].interest == 750.00
    assert rows[0].principal == pytest.approx(361.66, abs=0.01)
    assert rows[-1].date == MATURITY
    assert rows[-1].closing_balance == 0
    s = summarise(rows)
    assert s.payoff_date == MATURITY
    assert s.total_principal == pytest.approx(200_000, abs=0.05)
    assert s.total_interest == pytest.approx(1111.6649 * 300 - 200_000, abs=5)


def test_rate_change_recalculates_payment_over_remaining_term():
    rows = build_schedule(terms(fallback_rate=0.06, rate_periods=FIX), 200_000, START)
    fixed, after = rows[23], rows[24]
    assert fixed.date == date(2028, 1, 1) and fixed.annual_rate == 0.045
    assert after.date == date(2028, 2, 1) and after.annual_rate == 0.06
    assert after.payment == pytest.approx(annuity_payment(fixed.closing_balance, 0.06, 276), abs=0.02)
    assert len(rows) == 300 and rows[-1].closing_balance == 0


def test_reduce_term_overpayment_keeps_shortening_after_rate_change():
    base = build_schedule(terms(fallback_rate=0.06, rate_periods=FIX), 200_000, START)
    over = build_schedule(
        terms(fallback_rate=0.06, rate_periods=FIX), 200_000, START, [(date(2027, 1, 1), 10_000)]
    )
    assert over[11].overpayment == 10_000
    assert over[12].payment == base[12].payment  # same payment until the rate changes
    assert len(over) < len(base) - 12
    assert summarise(over).total_interest < summarise(base).total_interest - 10_000


def test_reduce_payment_keeps_maturity_and_lowers_payment():
    rows = build_schedule(
        terms(overpayment_effect="reduce_payment"), 200_000, START, [(date(2027, 1, 1), 10_000)]
    )
    assert len(rows) == 300 and rows[-1].date == MATURITY
    assert rows[12].payment < rows[11].payment - 50


def test_overpayments_on_or_before_balance_date_are_ignored():
    rows = build_schedule(terms(), 200_000, START, [(date(2025, 12, 1), 5_000), (START, 5_000)])
    assert all(r.overpayment == 0 for r in rows)


def test_mid_month_overpayment_applies_at_next_payment():
    rows = build_schedule(terms(), 200_000, START, [(date(2026, 3, 15), 1_000)])
    assert rows[1].overpayment == 0
    assert rows[2].date == date(2026, 4, 1) and rows[2].overpayment == 1_000


def test_interest_only_pays_interest_then_balloon():
    rows = build_schedule(terms(repayment_type="interest_only", maturity=date(2027, 1, 1)), 120_000, START)
    assert len(rows) == 12
    assert all(r.principal == 0 and r.payment == 450.00 for r in rows[:-1])
    assert rows[-1].principal == 120_000 and rows[-1].closing_balance == 0


def test_payment_override_is_used():
    periods = (RatePeriod(start=START, annual_rate=0.045, payment_override=1_500),)
    rows = build_schedule(terms(rate_periods=periods), 200_000, START)
    assert rows[0].payment == 1_500
    assert len(rows) < 300 and rows[-1].closing_balance == 0


def test_balance_on_and_until():
    rows = build_schedule(terms(), 200_000, START, until=date(2026, 6, 30))
    assert len(rows) == 5
    assert balance_on(rows, date(2026, 1, 15), 200_000) == 200_000
    assert balance_on(rows, date(2026, 3, 1), 200_000) == rows[1].closing_balance


def test_payments_to_clear_round_trip():
    payment = annuity_payment(150_000, 0.05, 240)
    assert payments_to_clear(150_000, 0.05, payment) == 240
    assert payments_to_clear(150_000, 0.05, 100) is None  # below the £625 monthly interest
    assert payments_to_clear(1_200, 0.0, 100) == 12
