"""Mortgage and loan amortisation with rate periods and overpayments.

Monthly model. On each payment date:
    interest  = balance * annual_rate / 12
    payment   = level annuity payment, recalculated when the rate changes (and after an
                overpayment when overpayment_effect == "reduce_payment")
    principal = payment - interest
Overpayments are applied straight after the first payment on or after their date.

Term handling on a recalculation:
    reduce_payment: clear the balance by the maturity date (payments shrink after overpaying).
    reduce_term:    keep the *effective* remaining term, i.e. the number of payments the old payment
                    needed at the old rate. Overpaying therefore keeps shortening the loan across
                    later rate changes instead of silently turning into lower payments.

UK lenders often accrue interest daily, so real statements drift slightly from this model. The app
re-anchors by building every schedule from the latest statement balance.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .dates import add_months, clamp_day, months_between

MONEY_EPS = 0.005


@dataclass(frozen=True)
class RatePeriod:
    start: date
    annual_rate: float
    end: date | None = None  # inclusive; None = open-ended
    payment_override: float | None = None  # lender-quoted payment, used instead of the formula


@dataclass(frozen=True)
class LoanTerms:
    maturity: date  # date of the final scheduled payment
    fallback_rate: float  # used on payment dates that no rate period covers (e.g. after a fix)
    rate_periods: tuple[RatePeriod, ...] = ()
    payment_day: int = 1
    repayment_type: str = "repayment"  # "repayment" | "interest_only"
    overpayment_effect: str = "reduce_term"  # "reduce_term" | "reduce_payment"


@dataclass(frozen=True)
class ScheduleRow:
    date: date
    annual_rate: float
    opening_balance: float
    payment: float  # scheduled payment (interest + principal), excluding any overpayment
    interest: float
    principal: float
    overpayment: float
    closing_balance: float


@dataclass(frozen=True)
class ScheduleSummary:
    n_payments: int
    total_interest: float
    total_principal: float
    total_overpayments: float
    payoff_date: date | None  # None when the schedule stops before the balance reaches zero


def annuity_payment(balance: float, annual_rate: float, n_payments: int) -> float:
    """Level monthly payment that repays `balance` over `n_payments` at `annual_rate`."""
    if balance <= 0:
        return 0.0
    if n_payments <= 0:
        return balance
    r = annual_rate / 12.0
    if abs(r) < 1e-12:
        return balance / n_payments
    return balance * r / (1.0 - (1.0 + r) ** -n_payments)


def payments_to_clear(balance: float, annual_rate: float, payment: float) -> int | None:
    """Whole payments needed to clear `balance` at `payment` per month. None if never cleared."""
    if balance <= 0:
        return 0
    if payment <= 0:
        return None
    r = annual_rate / 12.0
    if abs(r) < 1e-12:
        return math.ceil(balance / payment - 1e-6)
    x = 1.0 - balance * r / payment
    if x <= 0:
        return None  # payment does not even cover the interest
    return math.ceil(-math.log(x) / math.log(1.0 + r) - 1e-6)


def rate_period_on(terms: LoanTerms, on: date) -> RatePeriod | None:
    """Rate period covering `on`; the latest start wins if periods overlap."""
    covering = [p for p in terms.rate_periods if p.start <= on and (p.end is None or on <= p.end)]
    return max(covering, key=lambda p: p.start) if covering else None


def _payment_on_or_after(d: date, payment_day: int, strictly_after: bool) -> date:
    candidate = clamp_day(d.year, d.month, payment_day)
    if candidate < d or (strictly_after and candidate == d):
        nxt = add_months(date(d.year, d.month, 1), 1)
        candidate = clamp_day(nxt.year, nxt.month, payment_day)
    return candidate


def first_payment_after(d: date, payment_day: int) -> date:
    return _payment_on_or_after(d, payment_day, strictly_after=True)


def build_schedule(
    terms: LoanTerms,
    balance: float,
    balance_date: date,
    overpayments: Iterable[tuple[date, float]] = (),
    until: date | None = None,
    max_rows: int = 1200,
) -> list[ScheduleRow]:
    """Schedule from a known `balance` on `balance_date` until repaid, `until`, or `max_rows`.

    `balance` must already include the effect of every payment and overpayment dated on or
    before `balance_date`; such overpayments are ignored here.
    """
    extra: dict[date, float] = defaultdict(float)
    for when, amount in overpayments:
        if when > balance_date and amount > 0:
            extra[_payment_on_or_after(when, terms.payment_day, strictly_after=False)] += amount

    interest_only = terms.repayment_type == "interest_only"
    rows: list[ScheduleRow] = []
    pay_date = first_payment_after(balance_date, terms.payment_day)
    payment: float | None = None
    current_rate: float | None = None
    recalc = True

    while balance > MONEY_EPS and len(rows) < max_rows:
        if until is not None and pay_date > until:
            break
        period = rate_period_on(terms, pay_date)
        rate = period.annual_rate if period else terms.fallback_rate
        remaining = max(months_between(pay_date, terms.maturity) + 1, 1)
        interest = balance * rate / 12.0

        if interest_only:
            scheduled = interest
        else:
            if rate != current_rate:
                recalc = True
            if recalc:
                if period is not None and period.payment_override is not None:
                    payment = period.payment_override
                else:
                    n = remaining
                    if (
                        payment is not None
                        and current_rate is not None
                        and terms.overpayment_effect == "reduce_term"
                    ):
                        effective = payments_to_clear(balance, current_rate, payment)
                        if effective is not None:
                            n = max(min(n, effective), 1)
                    payment = annuity_payment(balance, rate, n)
                recalc = False
            scheduled = payment if payment is not None else interest
        current_rate = rate

        principal = scheduled - interest
        if remaining <= 1 or principal >= balance - MONEY_EPS:
            principal = balance
            scheduled = interest + balance
        overpaid = min(extra.get(pay_date, 0.0), max(balance - principal, 0.0))
        closing = balance - principal - overpaid

        rows.append(
            ScheduleRow(
                date=pay_date,
                annual_rate=rate,
                opening_balance=round(balance, 2),
                payment=round(scheduled, 2),
                interest=round(interest, 2),
                principal=round(principal, 2),
                overpayment=round(overpaid, 2),
                closing_balance=round(max(closing, 0.0), 2),
            )
        )
        if overpaid > 0 and terms.overpayment_effect == "reduce_payment":
            recalc = True
        balance = closing
        nxt = add_months(date(pay_date.year, pay_date.month, 1), 1)
        pay_date = clamp_day(nxt.year, nxt.month, terms.payment_day)

    return rows


def balance_on(rows: list[ScheduleRow], on: date, default: float) -> float:
    """Outstanding balance on `on`: closing balance of the last payment on or before it."""
    result = default
    for row in rows:
        if row.date > on:
            break
        result = row.closing_balance
    return result


def summarise(rows: list[ScheduleRow]) -> ScheduleSummary:
    paid_off = bool(rows) and rows[-1].closing_balance <= MONEY_EPS
    return ScheduleSummary(
        n_payments=len(rows),
        total_interest=round(sum(r.interest for r in rows), 2),
        total_principal=round(sum(r.principal for r in rows), 2),
        total_overpayments=round(sum(r.overpayment for r in rows), 2),
        payoff_date=rows[-1].date if paid_off else None,
    )
