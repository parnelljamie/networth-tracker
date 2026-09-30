from datetime import date

import pytest

from app.engine.recurring import Plan, amount_on, gross_amount_on, occurrence_dates, occurrences


def test_month_end_start_keeps_its_day_where_possible():
    p = Plan(100, "monthly", date(2026, 1, 31))
    assert occurrence_dates(p, date(2026, 1, 1), date(2026, 4, 30)) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_day_of_month_before_start_rolls_to_next_period():
    p = Plan(100, "monthly", date(2026, 9, 15), day_of_month=1)
    assert occurrence_dates(p, date(2026, 9, 1), date(2026, 11, 30)) == [
        date(2026, 10, 1),
        date(2026, 11, 1),
    ]


def test_window_long_after_start():
    p = Plan(100, "monthly", date(2020, 1, 1))
    assert occurrence_dates(p, date(2026, 9, 10), date(2026, 12, 31)) == [
        date(2026, 10, 1),
        date(2026, 11, 1),
        date(2026, 12, 1),
    ]


def test_weekly_and_fortnightly():
    weekly = Plan(25, "weekly", date(2026, 1, 1))
    assert occurrence_dates(weekly, date(2026, 1, 10), date(2026, 1, 31)) == [
        date(2026, 1, 15),
        date(2026, 1, 22),
        date(2026, 1, 29),
    ]
    fortnightly = Plan(25, "fortnightly", date(2026, 1, 1))
    assert occurrence_dates(fortnightly, date(2026, 1, 1), date(2026, 2, 1)) == [
        date(2026, 1, 1),
        date(2026, 1, 15),
        date(2026, 1, 29),
    ]


def test_quarterly_annual_and_inclusive_end_date():
    q = Plan(300, "quarterly", date(2026, 1, 10))
    assert occurrence_dates(q, date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 1, 10),
        date(2026, 4, 10),
        date(2026, 7, 10),
        date(2026, 10, 10),
    ]
    a = Plan(1_000, "annually", date(2024, 4, 6), end=date(2026, 4, 6))
    assert occurrence_dates(a, date(2020, 1, 1), date(2030, 1, 1)) == [
        date(2024, 4, 6),
        date(2025, 4, 6),
        date(2026, 4, 6),
    ]
    assert occurrence_dates(a, date(2026, 4, 7), date(2030, 1, 1)) == []


def test_escalation_on_anniversaries_and_tax_relief():
    p = Plan(100, "monthly", date(2026, 1, 1), annual_increase_rate=0.05)
    assert amount_on(p, date(2026, 12, 1)) == pytest.approx(100)
    assert amount_on(p, date(2027, 1, 1)) == pytest.approx(105)
    assert amount_on(p, date(2028, 2, 1)) == pytest.approx(110.25)

    sipp = Plan(80, "monthly", date(2026, 1, 1), tax_relief_rate=0.25)
    assert gross_amount_on(sipp, date(2026, 5, 1)) == pytest.approx(100)
    occ = occurrences(sipp, date(2026, 1, 1), date(2026, 3, 1))
    assert [d for d, _ in occ] == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    assert [a for _, a in occ] == pytest.approx([100, 100, 100])
    assert [a for _, a in occurrences(sipp, date(2026, 1, 1), date(2026, 1, 1), gross=False)] == [80]


def test_unknown_frequency_raises():
    with pytest.raises(ValueError):
        occurrence_dates(Plan(1, "daily", date(2026, 1, 1)), date(2026, 1, 1), date(2026, 2, 1))
