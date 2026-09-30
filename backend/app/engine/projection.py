"""Month-by-month net worth projection across accounts and people.

Account kinds
    growth  investments, pensions, cash: value compounds at (annual_rate + scenario adjustment
            - annual_fee_rate) over the actual days in each interval, then that interval's
            contributions/withdrawals/lump sums are added. Money added mid-interval starts
            growing next interval (slightly conservative). Values never go below zero.
    model   property and other assets: closed-form grow_value() from today's value.
    loan    mortgages and loans: amortisation schedule from today's balance, including planned
            overpayments (recurring plans of kind "overpayment" and positive lump sums).
    static  held flat (credit cards, excluded-from-growth items).

Cash movements dated on or before `today` are assumed to be inside today's value already.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from .amortisation import LoanTerms, ScheduleRow, balance_on, build_schedule
from .dates import projection_dates, years_between
from .db_pension import DbPensionTerms, capitalised_value
from .growth import deflate, grow_value, growth_factor
from .recurring import Plan, occurrences

LIABILITY_CATEGORIES = frozenset({"mortgage", "loan", "credit_card", "other_liability"})


@dataclass(frozen=True)
class ProjectionAccount:
    id: int
    category: str
    kind: str  # "growth" | "model" | "loan" | "static" | "db"
    value: float  # today's value; liabilities as a positive amount owed
    owners: dict[int, float] = field(default_factory=dict)  # person_id -> share
    annual_rate: float = 0.0  # growth: expected return or interest; model: +appreciation/-depreciation
    annual_fee_rate: float = 0.0
    model_method: str = "compound"
    floor: float | None = None
    cap: float | None = None
    loan_terms: LoanTerms | None = None
    db_terms: DbPensionTerms | None = None  # kind "db": capitalised defined-benefit pension
    scenario_adjustable: bool = True  # False for cash: market scenarios don't move savings rates

    @property
    def is_liability(self) -> bool:
        return self.category in LIABILITY_CATEGORIES


@dataclass(frozen=True)
class ProjectionFlow:
    account_id: int
    plan: Plan
    kind: str = "contribution"  # "contribution" (gross incl. tax relief) | "withdrawal" | "overpayment"


@dataclass(frozen=True)
class LumpSum:
    account_id: int
    date: date
    amount: float  # + into an asset or overpaying a loan, - out of an asset


@dataclass(frozen=True)
class RateChange:
    account_id: int
    date: date
    annual_rate: float  # replaces the account's annual_rate from this date (e.g. de-risking)


@dataclass(frozen=True)
class Assumptions:
    inflation_rate: float = 0.025
    return_adjustment: float = 0.0  # scenario shift added to scenario_adjustable growth accounts
    real_terms: bool = False  # deflate every output value to today's money


@dataclass
class ProjectionResult:
    dates: list[date]
    total: list[float]
    by_account: dict[int, list[float]]  # signed: liabilities negative
    by_category: dict[str, list[float]]
    by_person: dict[int, list[float]]
    contributions: list[float]  # cumulative net money added to growth accounts since today
    loan_schedules: dict[int, list[ScheduleRow]]


def _growth_series(
    acct: ProjectionAccount,
    dates: Sequence[date],
    flows: list[ProjectionFlow],
    lumps: list[LumpSum],
    rate_changes: list[RateChange],
    assumptions: Assumptions,
) -> tuple[list[float], list[float]]:
    today, horizon = dates[0], dates[-1]
    moves: list[tuple[date, float]] = []
    for f in flows:
        if f.kind == "overpayment":
            continue
        sign = -1.0 if f.kind == "withdrawal" else 1.0
        gross = f.kind == "contribution"
        for d, amount in occurrences(f.plan, today + timedelta(days=1), horizon, gross=gross):
            moves.append((d, sign * amount))
    moves.extend((ls.date, ls.amount) for ls in lumps if today < ls.date <= horizon)
    moves.sort(key=lambda m: m[0])
    changes = sorted(rate_changes, key=lambda c: c.date)

    values, added = [acct.value], [0.0]
    v, cum, j = acct.value, 0.0, 0
    for m in range(1, len(dates)):
        d0, d1 = dates[m - 1], dates[m]
        base = acct.annual_rate
        for c in changes:
            if c.date <= d0:
                base = c.annual_rate
        adjustment = assumptions.return_adjustment if acct.scenario_adjustable else 0.0
        v *= growth_factor(base + adjustment - acct.annual_fee_rate, years_between(d0, d1))
        while j < len(moves) and moves[j][0] <= d1:
            v += moves[j][1]
            cum += moves[j][1]
            j += 1
        v = max(v, 0.0)
        values.append(v)
        added.append(cum)
    return values, added


def project(
    accounts: Iterable[ProjectionAccount],
    flows: Iterable[ProjectionFlow],
    lump_sums: Iterable[LumpSum],
    today: date,
    months: int,
    assumptions: Assumptions | None = None,
    rate_changes: Iterable[RateChange] = (),
) -> ProjectionResult:
    assumptions = assumptions or Assumptions()
    dates = projection_dates(today, months)
    n, horizon = len(dates), dates[-1]

    flows_by: dict[int, list[ProjectionFlow]] = defaultdict(list)
    for f in flows:
        flows_by[f.account_id].append(f)
    lumps_by: dict[int, list[LumpSum]] = defaultdict(list)
    for ls in lump_sums:
        lumps_by[ls.account_id].append(ls)
    changes_by: dict[int, list[RateChange]] = defaultdict(list)
    for c in rate_changes:
        changes_by[c.account_id].append(c)

    result = ProjectionResult(
        dates=dates,
        total=[0.0] * n,
        by_account={},
        by_category={},
        by_person={},
        contributions=[0.0] * n,
        loan_schedules={},
    )
    years = [years_between(today, d) for d in dates]

    def to_output(x: float, i: int) -> float:
        return deflate(x, assumptions.inflation_rate, years[i]) if assumptions.real_terms else x

    for acct in accounts:
        if acct.kind == "growth":
            values, added = _growth_series(
                acct, dates, flows_by[acct.id], lumps_by[acct.id], changes_by[acct.id], assumptions
            )
            for i in range(n):
                result.contributions[i] += to_output(added[i], i)
        elif acct.kind == "model":
            values = [
                grow_value(acct.value, acct.annual_rate, years[i], acct.model_method, acct.floor, acct.cap)
                for i in range(n)
            ]
        elif acct.kind == "loan":
            if acct.loan_terms is None:
                raise ValueError(f"account {acct.id}: loan projection needs loan_terms")
            overpayments: list[tuple[date, float]] = []
            for f in flows_by[acct.id]:
                if f.kind == "overpayment":
                    overpayments += occurrences(f.plan, today + timedelta(days=1), horizon, gross=False)
            overpayments += [(ls.date, ls.amount) for ls in lumps_by[acct.id] if ls.amount > 0]
            rows = build_schedule(acct.loan_terms, acct.value, today, overpayments, until=horizon)
            result.loan_schedules[acct.id] = rows
            values = [balance_on(rows, d, acct.value) for d in dates]
        elif acct.kind == "static":
            values = [acct.value] * n
        elif acct.kind == "db":
            if acct.db_terms is None:
                raise ValueError(f"account {acct.id}: db projection needs db_terms")
            # Revaluation and pension increases follow the scenario's inflation assumption.
            values = [capitalised_value(acct.db_terms, d, assumptions.inflation_rate) for d in dates]
        else:
            raise ValueError(f"account {acct.id}: unknown projection kind {acct.kind!r}")

        sign = -1.0 if acct.is_liability else 1.0
        series = [round(sign * to_output(values[i], i), 2) for i in range(n)]
        result.by_account[acct.id] = series
        category = result.by_category.setdefault(acct.category, [0.0] * n)
        for i, x in enumerate(series):
            category[i] += x
            result.total[i] += x
        for person_id, share in acct.owners.items():
            person = result.by_person.setdefault(person_id, [0.0] * n)
            for i, x in enumerate(series):
                person[i] += x * share

    result.total = [round(x, 2) for x in result.total]
    result.contributions = [round(x, 2) for x in result.contributions]
    result.by_category = {k: [round(x, 2) for x in v] for k, v in result.by_category.items()}
    result.by_person = {k: [round(x, 2) for x in v] for k, v in result.by_person.items()}
    return result


def first_date_reaching(dates: Sequence[date], series: Sequence[float], target: float) -> date | None:
    """First projection date on which `series` is at or above `target` (milestones)."""
    for d, x in zip(dates, series, strict=True):
        if x >= target:
            return d
    return None
