"""docs/03-domain-logic.md §7 "Projections". Builds engine.projection inputs from the DB, calls
the engine, and adds milestones. Results are cached in-memory keyed by parameters plus a
data-version counter bumped by any write that could change a projection (pattern: the search
cache in price_service, but invalidated instead of time-limited)."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import Category, ScenarioEventKind, ValuationMethod, Wrapper
from app.core.errors import DomainError
from app.engine import amortisation
from app.engine import monte_carlo as engine_monte_carlo
from app.engine import projection as engine_projection
from app.engine.dates import add_months
from app.models.accounts import Account
from app.models.loans import LoanRatePeriod
from app.models.people import Person
from app.models.positions import Position
from app.models.recurring import RecurringPlan
from app.models.scenarios import Scenario, ScenarioEvent
from app.services import (
    db_pension_service,
    loan_service,
    price_service,
    recurring_service,
    scenario_service,
    settings_service,
    valuation_service,
)

MILESTONE_STEP_GBP = 100_000
MILESTONE_CAP_GBP = 2_000_000

# ---------------------------------------------------------------------------
# Data-version cache
# ---------------------------------------------------------------------------

_data_version = 0
_cache: dict[tuple, Any] = {}


def bump_data_version() -> None:
    global _data_version
    _data_version += 1
    _cache.clear()


def current_data_version() -> int:
    return _data_version


def _cache_get(key: tuple) -> Any | None:
    return _cache.get(key)


def _cache_set(key: tuple, value: Any) -> Any:
    _cache[key] = value
    return value


# ---------------------------------------------------------------------------
# Account -> engine.ProjectionAccount mapping (docs/03-domain-logic.md §7 table)
# ---------------------------------------------------------------------------


def account_projection_kind(account: Account) -> str:
    if account.valuation_method == ValuationMethod.amortising:
        return "loan"
    if account.valuation_method == ValuationMethod.defined_benefit:
        return "db"
    if account.valuation_method == ValuationMethod.model:
        return "model"
    if account.valuation_method == ValuationMethod.holdings:
        return "growth"
    # balance method
    if account.category in (Category.investment, Category.pension) and account.wrapper != Wrapper.db_pension:
        return "growth"
    if account.category == Category.cash:
        return "growth"
    if account.category == Category.credit_card and account.interest_rate:
        return "growth"
    return "static"  # db_pension and other balance-method liabilities with no rate


def _holdings_weighted_rate(db: Session, account: Account, default_rates: dict[str, float]) -> float:
    positions = list(db.scalars(select(Position).where(Position.account_id == account.id)).all())
    on = date_today()
    total_value = 0.0
    weighted = 0.0
    for pos in positions:
        result = price_service.price_gbp(db, pos.instrument, on, live=True)
        value = pos.units * result.price_gbp
        total_value += value
        weighted += value * default_rates.get(pos.instrument.asset_class.value, 0.0)
    if total_value <= 0:
        return 0.0
    return weighted / total_value


def _growth_rate(db: Session, account: Account, default_rates: dict[str, float]) -> float:
    if account.expected_return_rate is not None:
        return account.expected_return_rate
    if account.valuation_method == ValuationMethod.holdings:
        return _holdings_weighted_rate(db, account, default_rates)
    return default_rates.get("multi_asset", 0.05)


def _build_account(
    db: Session, account: Account, scenario: Scenario, default_rates: dict[str, float]
) -> engine_projection.ProjectionAccount | None:
    on = date_today()
    kind = account_projection_kind(account)
    owners = {o.person_id: o.share for o in account.owners}
    annual_fee_rate = account.annual_fee_rate or 0.0

    if kind == "growth":
        valuation = valuation_service.value_account(db, account, on, live=True)
        value = abs(valuation.value_gbp)
        if account.category in (Category.cash, Category.credit_card):
            rate = account.interest_rate if account.interest_rate is not None else default_rates.get("cash", 0.035)
            scenario_adjustable = False
        else:
            rate = _growth_rate(db, account, default_rates)
            scenario_adjustable = True
        return engine_projection.ProjectionAccount(
            id=account.id,
            category=account.category.value,
            kind="growth",
            value=value,
            owners=owners,
            annual_rate=rate,
            annual_fee_rate=annual_fee_rate,
            scenario_adjustable=scenario_adjustable,
        )

    if kind == "model":
        valuation = valuation_service.value_account(db, account, on, live=True)
        value = abs(valuation.value_gbp)
        gm = account.growth_model
        if account.category == Category.property:
            rate = (
                scenario.property_growth_rate
                if scenario.property_growth_rate is not None
                else (gm.annual_rate if gm is not None else default_rates.get("property", 0.03))
            )
        else:
            rate = gm.annual_rate if gm is not None else 0.0
        method = gm.method.value if gm is not None else "compound"
        floor = gm.floor_value_gbp if gm is not None else None
        cap = gm.cap_value_gbp if gm is not None else None
        return engine_projection.ProjectionAccount(
            id=account.id,
            category=account.category.value,
            kind="model",
            value=value,
            owners=owners,
            annual_rate=rate,
            model_method=method,
            floor=floor,
            cap=cap,
        )

    if kind == "loan":
        try:
            balance, _anchor = loan_service.estimated_balance_today(db, account, on)
            terms = loan_service.terms_for(account)
        except DomainError:
            return None  # incomplete loan setup — skip rather than 500 the whole projection
        return engine_projection.ProjectionAccount(
            id=account.id,
            category=account.category.value,
            kind="loan",
            value=balance,
            owners=owners,
            loan_terms=terms,
        )

    if kind == "db":
        try:
            terms = db_pension_service.terms_for(account)
        except DomainError:
            return None  # scheme details missing: skip rather than 500 the whole projection
        valuation = valuation_service.value_account(db, account, on, live=True)
        return engine_projection.ProjectionAccount(
            id=account.id,
            category=account.category.value,
            kind="db",
            value=abs(valuation.value_gbp),
            owners=owners,
            db_terms=terms,
        )

    # static
    valuation = valuation_service.value_account(db, account, on, live=True)
    return engine_projection.ProjectionAccount(
        id=account.id,
        category=account.category.value,
        kind="static",
        value=abs(valuation.value_gbp),
        owners=owners,
    )


# ---------------------------------------------------------------------------
# Flows: recurring plans, adjusted by scenario events
# ---------------------------------------------------------------------------


def _plan_flows(
    plan: RecurringPlan, events_by_plan: dict[int, list[ScenarioEvent]]
) -> list[engine_projection.ProjectionFlow]:
    """docs §7: stop_plan sets the engine plan's end to the event date; change_plan_amount ends
    the plan the day before and adds a copy starting on the event date with the new amount."""
    base = recurring_service.to_engine(plan)
    events = sorted(events_by_plan.get(plan.id, []), key=lambda e: e.date)
    segments = [base]
    for event in events:
        current = segments[-1]
        if event.kind == ScenarioEventKind.stop_plan:
            new_end = event.date if current.end is None else min(current.end, event.date)
            segments[-1] = dc_replace(current, end=new_end)
            break
        if event.kind == ScenarioEventKind.change_plan_amount and event.amount_gbp is not None:
            cutoff = event.date - timedelta(days=1)
            new_end = cutoff if current.end is None else min(current.end, cutoff)
            segments[-1] = dc_replace(current, end=new_end)
            segments.append(dc_replace(current, start=event.date, end=base.end, amount=event.amount_gbp))
    return [
        engine_projection.ProjectionFlow(account_id=plan.account_id, plan=seg, kind=plan.kind.value)
        for seg in segments
    ]


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


def _networth_milestones(dates: list[date], series: list[float], person_id: int | None) -> list[dict]:
    on = dates[0]
    current = series[0]
    out: list[dict] = []
    target = (int(current // MILESTONE_STEP_GBP) + 1) * MILESTONE_STEP_GBP
    while target <= MILESTONE_CAP_GBP:
        d = engine_projection.first_date_reaching(dates, series, target)
        if d is not None and d > on:
            out.append(
                {
                    "kind": "networth_target",
                    "label": f"£{target:,.0f}",
                    "date": d,
                    "person_id": person_id,
                }
            )
        target += MILESTONE_STEP_GBP
    return out


def _mortgage_free_milestones(
    projection_accounts: list[engine_projection.ProjectionAccount],
    loan_schedules: dict[int, list],
    accounts_by_id: dict[int, Account],
) -> list[dict]:
    out: list[dict] = []
    for acct in projection_accounts:
        if acct.kind != "loan":
            continue
        rows = loan_schedules.get(acct.id)
        if not rows:
            continue
        summary = amortisation.summarise(rows)
        if summary.payoff_date is None:
            continue
        name = accounts_by_id[acct.id].name if acct.id in accounts_by_id else "Loan"
        label = "Mortgage-free" if acct.category == Category.mortgage.value else f"{name} paid off"
        out.append({"kind": "mortgage_free", "label": label, "date": summary.payoff_date, "person_id": None})
    return out


def _people_milestones(db: Session, on: date, pension_access_age: int, person_id: int | None) -> list[dict]:
    out: list[dict] = []
    people = list(db.scalars(select(Person).where(Person.is_archived.is_(False))).all())
    for person in people:
        if person.date_of_birth is None:
            continue
        if person_id is not None and person.id != person_id:
            continue
        access_date = add_months(person.date_of_birth, pension_access_age * 12)
        if access_date >= on:
            out.append(
                {
                    "kind": "pension_access",
                    "label": f"{person.name}'s pension access",
                    "date": access_date,
                    "person_id": person.id,
                }
            )
        retirement_date = add_months(person.date_of_birth, person.retirement_age * 12)
        if retirement_date >= on:
            out.append(
                {
                    "kind": "retirement",
                    "label": f"{person.name}'s retirement",
                    "date": retirement_date,
                    "person_id": person.id,
                }
            )
    return out


def _fix_end_milestones(db: Session, on: date) -> list[dict]:
    rows = list(
        db.scalars(
            select(LoanRatePeriod).where(
                LoanRatePeriod.start_date <= on, LoanRatePeriod.end_date.is_not(None), LoanRatePeriod.end_date >= on
            )
        ).all()
    )
    out: list[dict] = []
    for rp in rows:
        account = db.get(Account, rp.account_id)
        name = account.name if account is not None else "Loan"
        out.append(
            {"kind": "fix_ends", "label": f"{name} fix ends", "date": rp.end_date, "person_id": None}
        )
    return out


def _scenario_event_milestones(events: list[ScenarioEvent], on: date) -> list[dict]:
    return [
        {"kind": "scenario_event", "label": e.label, "date": e.date, "person_id": None}
        for e in events
        if e.date >= on
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class _Inputs:
    on: date
    scenario: Scenario
    settings_map: dict[str, Any]
    accounts_by_id: dict[int, Account]
    projection_accounts: list[engine_projection.ProjectionAccount]
    flows: list[engine_projection.ProjectionFlow]
    lump_sums: list[engine_projection.LumpSum]
    rate_changes: list[engine_projection.RateChange]
    events: list[ScenarioEvent]
    assumptions: engine_projection.Assumptions


def _build_inputs(db: Session, scenario_id: int | None, real_terms: bool) -> _Inputs:
    """Engine inputs shared by the deterministic projection and the Monte Carlo range."""
    scenario = (
        scenario_service.get_scenario(db, scenario_id)
        if scenario_id is not None
        else scenario_service.get_default_scenario(db)
    )
    settings_map = settings_service.get_all(db)
    default_rates: dict[str, float] = settings_map.get("default_return_rates", {})
    on = date_today()

    accounts = list(db.scalars(select(Account).where(Account.is_archived.is_(False))).all())
    accounts_by_id = {a.id: a for a in accounts}
    projection_accounts: list[engine_projection.ProjectionAccount] = []
    for account in accounts:
        pa = _build_account(db, account, scenario, default_rates)
        if pa is not None:
            projection_accounts.append(pa)

    plans = [p for p in recurring_service.list_plans(db) if p.is_active]
    events = scenario_service.list_events(db, scenario.id)
    events_by_plan: dict[int, list[ScenarioEvent]] = {}
    for e in events:
        if e.plan_id is not None:
            events_by_plan.setdefault(e.plan_id, []).append(e)

    flows: list[engine_projection.ProjectionFlow] = []
    for plan in plans:
        flows.extend(_plan_flows(plan, events_by_plan))

    lump_sums = [
        engine_projection.LumpSum(account_id=e.account_id, date=e.date, amount=e.amount_gbp)
        for e in events
        if e.kind == ScenarioEventKind.lump_sum and e.account_id is not None and e.amount_gbp is not None
    ]
    rate_changes = [
        engine_projection.RateChange(account_id=e.account_id, date=e.date, annual_rate=e.rate)
        for e in events
        if e.kind == ScenarioEventKind.set_return_rate and e.account_id is not None and e.rate is not None
    ]

    assumptions = engine_projection.Assumptions(
        inflation_rate=(
            scenario.inflation_rate if scenario.inflation_rate is not None else settings_map.get("inflation_rate", 0.025)
        ),
        return_adjustment=scenario.return_adjustment,
        real_terms=real_terms,
    )

    return _Inputs(
        on=on,
        scenario=scenario,
        settings_map=settings_map,
        accounts_by_id=accounts_by_id,
        projection_accounts=projection_accounts,
        flows=flows,
        lump_sums=lump_sums,
        rate_changes=rate_changes,
        events=events,
        assumptions=assumptions,
    )


def build_projection(
    db: Session,
    person_id: int | None = None,
    scenario_id: int | None = None,
    months: int = 360,
    real_terms: bool = False,
    by_account: bool = False,
) -> dict:
    key = ("projection", _data_version, person_id, scenario_id, months, real_terms, by_account)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    inputs = _build_inputs(db, scenario_id, real_terms)
    on, settings_map, events = inputs.on, inputs.settings_map, inputs.events
    projection_accounts, accounts_by_id = inputs.projection_accounts, inputs.accounts_by_id
    assumptions = inputs.assumptions

    result = engine_projection.project(
        projection_accounts, inputs.flows, inputs.lump_sums, on, months, assumptions, inputs.rate_changes
    )

    n = len(result.dates)
    if person_id is not None:
        total = result.by_person.get(person_id, [0.0] * n)
        by_account_out: dict[int, list[float]] = {}
        by_category_out: dict[str, list[float]] = {}
        for acct in projection_accounts:
            share = acct.owners.get(person_id, 0.0)
            series = result.by_account[acct.id]
            scaled = [round(x * share, 2) for x in series]
            by_account_out[acct.id] = scaled
            cat_series = by_category_out.setdefault(acct.category, [0.0] * n)
            for i, x in enumerate(scaled):
                cat_series[i] += x
        by_category_out = {k: [round(x, 2) for x in v] for k, v in by_category_out.items()}
    else:
        total = result.total
        by_account_out = result.by_account
        by_category_out = result.by_category

    milestones: list[dict] = []
    milestones += _networth_milestones(result.dates, total, person_id)
    milestones += _mortgage_free_milestones(projection_accounts, result.loan_schedules, accounts_by_id)
    milestones += _people_milestones(db, on, settings_map.get("pension_access_age", 57), person_id)
    milestones += _fix_end_milestones(db, on)
    milestones += _scenario_event_milestones(events, on)
    milestones.sort(key=lambda m: m["date"])

    out = {
        "dates": result.dates,
        "total": total,
        "by_category": by_category_out,
        "by_person": result.by_person,
        "by_account": by_account_out if by_account else None,
        "contributions": result.contributions,
        "milestones": milestones,
        "assumptions": {
            "inflation_rate": assumptions.inflation_rate,
            "return_adjustment": assumptions.return_adjustment,
            "real_terms": assumptions.real_terms,
        },
    }
    return _cache_set(key, out)


def compare(
    db: Session, scenario_ids: list[int], person_id: int | None, months: int, real_terms: bool
) -> dict:
    key = ("compare", _data_version, tuple(sorted(scenario_ids)), person_id, months, real_terms)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    dates: list[date] = []
    series = []
    for scenario_id in scenario_ids:
        proj = build_projection(db, person_id, scenario_id, months, real_terms, by_account=False)
        if not dates:
            dates = proj["dates"]
        scenario = scenario_service.get_scenario(db, scenario_id)
        series.append({"scenario_id": scenario_id, "name": scenario.name, "total": proj["total"]})

    out = {"dates": dates, "series": series}
    return _cache_set(key, out)


MONTE_CARLO_PATHS = 1000
MONTE_CARLO_SEED = 20260919  # fixed, so the band doesn't jitter between page loads


def _risk_weights(db: Session, account: Account) -> dict[str, float]:
    """Asset-class mix that sets a growth account's volatility: its holdings by current value, or
    multi_asset for a balance-method investment/pension (or a holdings account with no prices).
    Cash and credit cards carry no market risk and get no weights."""
    if account.category in (Category.cash, Category.credit_card):
        return {}
    if account.valuation_method == ValuationMethod.holdings:
        on = date_today()
        by_class: dict[str, float] = {}
        for pos in db.scalars(select(Position).where(Position.account_id == account.id)).all():
            value = pos.units * price_service.price_gbp(db, pos.instrument, on, live=True).price_gbp
            if value > 0:
                cls = pos.instrument.asset_class.value
                by_class[cls] = by_class.get(cls, 0.0) + value
        total = sum(by_class.values())
        if total > 0:
            return {cls: v / total for cls, v in by_class.items()}
    return {"multi_asset": 1.0}


def build_monte_carlo(
    db: Session,
    person_id: int | None = None,
    scenario_id: int | None = None,
    months: int = 360,
    real_terms: bool = False,
) -> dict:
    """docs/03-domain-logic.md §10: p10–p90 of the projected total, from 1,000 market paths."""
    key = ("monte_carlo", _data_version, person_id, scenario_id, months, real_terms)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    inputs = _build_inputs(db, scenario_id, real_terms)
    risk_weights = {
        pa.id: weights
        for pa in inputs.projection_accounts
        if pa.kind == "growth"
        and (weights := _risk_weights(db, inputs.accounts_by_id[pa.id]))
    }
    volatility: dict[str, float] = inputs.settings_map.get("default_volatility", {})
    result = engine_monte_carlo.simulate(
        inputs.projection_accounts,
        inputs.flows,
        inputs.lump_sums,
        inputs.on,
        months,
        risk_weights,
        volatility,
        inputs.assumptions,
        inputs.rate_changes,
        person_id=person_id,
        paths=MONTE_CARLO_PATHS,
        seed=MONTE_CARLO_SEED,
    )
    out = {
        "dates": result.dates,
        "p10": result.percentiles[10],
        "p25": result.percentiles[25],
        "p50": result.percentiles[50],
        "p75": result.percentiles[75],
        "p90": result.percentiles[90],
        "deterministic": result.deterministic,
        "paths": result.paths,
    }
    return _cache_set(key, out)


def projected_pension_pot(
    db: Session, account: Account, scenario_id: int | None = None
) -> float | None:
    """Projected value of a single pension account at the account owner's retirement age (or in
    12 months if no owner has a date of birth), for the person page pension card (docs/05-ui.md)."""
    if account.category != Category.pension:
        return None
    owners = list(account.owners)
    person = next((o.person for o in owners if o.person.date_of_birth is not None), None)
    on = date_today()
    if person is None or person.date_of_birth is None:
        months = 12
    else:
        retirement_date = add_months(person.date_of_birth, person.retirement_age * 12)
        months = max(1, min(600, (retirement_date.year - on.year) * 12 + (retirement_date.month - on.month)))

    scenario = (
        scenario_service.get_scenario(db, scenario_id)
        if scenario_id is not None
        else scenario_service.get_default_scenario(db)
    )
    settings_map = settings_service.get_all(db)
    default_rates: dict[str, float] = settings_map.get("default_return_rates", {})
    pa = _build_account(db, account, scenario, default_rates)
    if pa is None:
        return None
    plans = [
        p for p in recurring_service.list_plans(db, account_id=account.id) if p.is_active
    ]
    flows = [
        engine_projection.ProjectionFlow(
            account_id=account.id, plan=recurring_service.to_engine(p), kind=p.kind.value
        )
        for p in plans
    ]
    assumptions = engine_projection.Assumptions(
        inflation_rate=settings_map.get("inflation_rate", 0.025),
        return_adjustment=scenario.return_adjustment,
        real_terms=False,
    )
    result = engine_projection.project([pa], flows, [], on, months, assumptions, [])
    series = result.by_account.get(account.id)
    if not series:
        return None
    return abs(series[-1])
