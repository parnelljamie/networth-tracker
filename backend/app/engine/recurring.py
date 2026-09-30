"""Dated occurrences of regular contributions, withdrawals and loan overpayments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .dates import clamp_day, months_between, whole_years_between

_DAY_STEP = {"weekly": 7, "fortnightly": 14}
_MONTH_STEP = {"monthly": 1, "quarterly": 3, "annually": 12}


@dataclass(frozen=True)
class Plan:
    amount: float  # net amount the person pays, before tax relief
    frequency: str  # weekly | fortnightly | monthly | quarterly | annually
    start: date
    end: date | None = None  # inclusive
    day_of_month: int | None = None  # month-based frequencies; None -> start.day
    annual_increase_rate: float = 0.0  # applied on each anniversary of `start`
    tax_relief_rate: float = 0.0  # 0.25 = relief at source: net 80 -> gross 100


def occurrence_dates(plan: Plan, from_date: date, to_date: date) -> list[date]:
    """Due dates within [from_date, to_date], both inclusive."""
    last = to_date if plan.end is None else min(to_date, plan.end)
    if last < plan.start or last < from_date:
        return []
    out: list[date] = []

    if plan.frequency in _DAY_STEP:
        step = _DAY_STEP[plan.frequency]
        d = plan.start
        if from_date > d:
            d += timedelta(days=-(-(from_date - d).days // step) * step)
        while d <= last:
            out.append(d)
            d += timedelta(days=step)
        return out

    if plan.frequency not in _MONTH_STEP:
        raise ValueError(f"unknown frequency {plan.frequency!r}")
    step = _MONTH_STEP[plan.frequency]
    dom = plan.day_of_month or plan.start.day

    def nth(i: int) -> date:
        y, m = divmod(plan.start.month - 1 + i * step, 12)
        return clamp_day(plan.start.year + y, m + 1, dom)

    i = 1 if nth(0) < plan.start else 0
    if from_date > plan.start:
        i = max(i, months_between(plan.start, from_date) // step - 1)
    d = nth(i)
    while d <= last:
        if d >= from_date and d >= plan.start:
            out.append(d)
        i += 1
        d = nth(i)
    return out


def amount_on(plan: Plan, on: date) -> float:
    """Net amount due on `on`, escalated by completed years since the plan started."""
    return plan.amount * (1.0 + plan.annual_increase_rate) ** whole_years_between(plan.start, on)


def gross_amount_on(plan: Plan, on: date) -> float:
    """Amount credited to the account, including tax relief."""
    return amount_on(plan, on) * (1.0 + plan.tax_relief_rate)


def occurrences(
    plan: Plan, from_date: date, to_date: date, gross: bool = True
) -> list[tuple[date, float]]:
    amount = gross_amount_on if gross else amount_on
    return [(d, amount(plan, d)) for d in occurrence_dates(plan, from_date, to_date)]
