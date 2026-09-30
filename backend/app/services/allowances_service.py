"""docs/03-domain-logic.md §8 "Allowances"."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import Category, PlanKind, TxnType, ValuationMethod, Wrapper
from app.engine import allowances as allowances_engine
from app.engine import recurring as recurring_engine
from app.engine.dates import tax_year_end as engine_tax_year_end
from app.engine.dates import tax_year_start as engine_tax_year_start
from app.models.accounts import Account
from app.models.people import Person
from app.models.recurring import RecurringPlan
from app.models.tax_year_rules import TaxYearRule
from app.services import ledger_service, recurring_service

# docs §8: holdings/balance accounts wrapped in an allowance-bearing wrapper.
RELEVANT_WRAPPERS = {
    Wrapper.isa,
    Wrapper.lisa,
    Wrapper.jisa,
    Wrapper.sipp,
    Wrapper.workplace_pension,
}


def _rules_for(db: Session, tax_year_start_year: int) -> allowances_engine.AllowanceRules:
    """docs §8: "Rules from tax_year_rules (latest row with tax_year_start <= year)"."""
    row = db.scalars(
        select(TaxYearRule)
        .where(TaxYearRule.tax_year_start <= tax_year_start_year)
        .order_by(TaxYearRule.tax_year_start.desc())
        .limit(1)
    ).first()
    if row is None:
        return allowances_engine.AllowanceRules()
    return allowances_engine.AllowanceRules(
        isa=row.isa_allowance_gbp,
        lisa=row.lisa_allowance_gbp,
        jisa=row.jisa_allowance_gbp,
        pension_annual=row.pension_annual_allowance_gbp,
        cash_isa_limit=row.cash_isa_limit_gbp,
    )


def _resolve_on(tax_year: int | None, today_: date) -> date:
    if tax_year is None:
        return today_
    start = date(tax_year, 4, 6)
    end = date(tax_year + 1, 4, 5)
    if today_ < start:
        return start
    if today_ > end:
        return end
    return today_


def usage(
    db: Session, tax_year: int | None = None, person_id: int | None = None
) -> list[dict]:
    resolved_on = _resolve_on(tax_year, date_today())
    ty_start = engine_tax_year_start(resolved_on)
    rules = _rules_for(db, ty_start.year)

    accounts = list(
        db.scalars(
            select(Account).where(
                Account.is_archived.is_(False), Account.wrapper.in_(RELEVANT_WRAPPERS)
            )
        ).all()
    )

    contributions: list[allowances_engine.Contribution] = []
    estimated_people: set[int] = set()

    for account in accounts:
        if len(account.owners) != 1:
            continue
        owner_id = account.owners[0].person_id
        is_cash = account.category == Category.cash

        if account.valuation_method == ValuationMethod.holdings:
            for t in ledger_service.confirmed_txns(db, account.id):
                if t.type != TxnType.DEPOSIT or t.amount_gbp <= 0:
                    continue
                contributions.append(
                    allowances_engine.Contribution(
                        person_id=owner_id,
                        date=t.date,
                        amount=t.amount_gbp,
                        wrapper=account.wrapper.value,
                        source=(t.contribution_source.value if t.contribution_source else "personal"),
                        is_cash=is_cash,
                    )
                )
        elif account.valuation_method == ValuationMethod.balance:
            plans = list(
                db.scalars(
                    select(RecurringPlan).where(
                        RecurringPlan.account_id == account.id,
                        RecurringPlan.is_active.is_(True),
                        RecurringPlan.kind == PlanKind.contribution,
                    )
                ).all()
            )
            for plan in plans:
                engine_plan = recurring_service.to_engine(plan)
                for d in recurring_engine.occurrence_dates(engine_plan, ty_start, resolved_on):
                    net = recurring_engine.amount_on(engine_plan, d)
                    gross = recurring_engine.gross_amount_on(engine_plan, d)
                    relief = gross - net
                    contributions.append(
                        allowances_engine.Contribution(
                            person_id=owner_id,
                            date=d,
                            amount=net,
                            wrapper=account.wrapper.value,
                            source=plan.contribution_source.value,
                            is_cash=is_cash,
                        )
                    )
                    if relief > 1e-6:
                        contributions.append(
                            allowances_engine.Contribution(
                                person_id=owner_id,
                                date=d,
                                amount=relief,
                                wrapper=account.wrapper.value,
                                source="tax_relief",
                                is_cash=is_cash,
                            )
                        )
                    estimated_people.add(owner_id)

    if person_id is not None:
        person_ids = [person_id]
    else:
        person_ids = list(db.scalars(select(Person.id).where(Person.is_archived.is_(False))).all())

    usage_by_person = allowances_engine.allowance_usage(contributions, resolved_on, rules, person_ids)
    people = {p.id: p for p in db.scalars(select(Person).where(Person.id.in_(person_ids))).all()}
    end = engine_tax_year_end(resolved_on)
    days_left = (end - resolved_on).days

    out: list[dict] = []
    for pid in person_ids:
        u = usage_by_person.get(pid)
        person = people.get(pid)
        if u is None or person is None:
            continue
        out.append(
            {
                "person_id": pid,
                "name": person.name,
                "tax_year": u.tax_year,
                "tax_year_end": u.tax_year_end,
                "days_left": days_left,
                "isa_used": round(u.isa_used, 2),
                "isa_limit": u.isa_limit,
                "isa_remaining": round(u.isa_remaining, 2),
                "lisa_used": round(u.lisa_used, 2),
                "lisa_limit": u.lisa_limit,
                "lisa_remaining": round(u.lisa_remaining, 2),
                "jisa_used": round(u.jisa_used, 2),
                "jisa_limit": u.jisa_limit,
                "jisa_remaining": round(u.jisa_remaining, 2),
                "pension_used": round(u.pension_used, 2),
                "pension_limit": u.pension_limit,
                "pension_remaining": round(u.pension_remaining, 2),
                "is_estimated": pid in estimated_people,
            }
        )
    return out
