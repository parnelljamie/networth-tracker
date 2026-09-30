"""Appreciation, depreciation and inflation maths."""

from __future__ import annotations

from datetime import date

from .dates import years_between


def monthly_rate(annual_rate: float) -> float:
    """Equivalent monthly compounding rate for an effective annual rate."""
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def growth_factor(annual_rate: float, years: float) -> float:
    """(1 + r) ** years. Non-positive years -> 1. A rate of -100% or worse -> 0."""
    if years <= 0:
        return 1.0
    base = 1.0 + annual_rate
    if base <= 0:
        return 0.0
    return base**years


def grow_value(
    value: float,
    annual_rate: float,
    years: float,
    method: str = "compound",
    floor: float | None = None,
    cap: float | None = None,
) -> float:
    """Model a value `years` after it was observed.

    compound: value * (1 + r) ** years
    linear:   value * (1 + r * years), never below zero
    `floor` only applies when depreciating and `cap` only when appreciating; neither can move the
    value past the observed starting value (a car observed below its floor stays where it is).
    """
    years = max(years, 0.0)
    if method == "compound":
        out = value * growth_factor(annual_rate, years)
    elif method == "linear":
        out = value * max(1.0 + annual_rate * years, 0.0)
    else:
        raise ValueError(f"unknown growth method {method!r}")
    if floor is not None and annual_rate < 0:
        out = max(out, min(floor, value))
    if cap is not None and annual_rate > 0:
        out = min(out, max(cap, value))
    return out


def value_on(
    value: float,
    observed_on: date,
    on: date,
    annual_rate: float,
    method: str = "compound",
    floor: float | None = None,
    cap: float | None = None,
) -> float:
    """grow_value() between two dates (actual/365.25)."""
    return grow_value(value, annual_rate, years_between(observed_on, on), method, floor, cap)


def deflate(value: float, inflation_rate: float, years: float) -> float:
    """Express a future nominal value in today's money."""
    factor = growth_factor(inflation_rate, years)
    return value / factor if factor > 0 else value
