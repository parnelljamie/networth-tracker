"""Calendar helpers shared by the engine. Pure: callers always pass the dates in."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

TAX_YEAR_START = (4, 6)  # UK tax year starts 6 April


def clamp_day(year: int, month: int, day: int) -> date:
    """date(year, month, day) with the day clamped to the month length (31 Feb -> 28/29 Feb)."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def add_months(d: date, months: int) -> date:
    """Shift by calendar months, clamping the day (31 Jan + 1 month -> 28/29 Feb)."""
    y, m = divmod(d.month - 1 + months, 12)
    return clamp_day(d.year + y, m + 1, d.day)


def month_end(d: date) -> date:
    return clamp_day(d.year, d.month, 31)


def months_between(a: date, b: date) -> int:
    """Calendar-month difference ignoring the day: months_between(15 Jan, 1 Mar) == 2."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def years_between(a: date, b: date) -> float:
    """Fractional years on an actual/365.25 basis. Negative when b is before a."""
    return (b - a).days / 365.25


def whole_years_between(a: date, b: date) -> int:
    """Completed anniversaries of `a` on or before `b` (never negative)."""
    years = b.year - a.year - ((b.month, b.day) < (a.month, a.day))
    return max(years, 0)


def tax_year_start(d: date) -> date:
    start = date(d.year, *TAX_YEAR_START)
    return start if d >= start else date(d.year - 1, *TAX_YEAR_START)


def tax_year_end(d: date) -> date:
    return date(tax_year_start(d).year + 1, 4, 5)


def tax_year_label(d: date) -> str:
    """'2026/27' for any date from 6 Apr 2026 to 5 Apr 2027."""
    y = tax_year_start(d).year
    return f"{y}/{(y + 1) % 100:02d}"


def daterange(start: date, end: date) -> list[date]:
    """Every calendar day from start to end inclusive (empty when end < start)."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def projection_dates(today: date, months: int) -> list[date]:
    """Projection timeline: index 0 is `today`, index m is the month end m months later.

    projection_dates(15 Sep 2026, 2) -> [15 Sep 2026, 31 Oct 2026, 30 Nov 2026]
    """
    return [today] + [month_end(add_months(today, m)) for m in range(1, months + 1)]
