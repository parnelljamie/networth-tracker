"""Defined-benefit pensions: build engine terms from the DB and derive display figures.
Maths lives in app/engine/db_pension.py."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.errors import DomainError
from app.engine import db_pension as engine
from app.engine.dates import add_months, years_between
from app.engine.growth import deflate
from app.models.accounts import Account
from app.models.db_pension import DbPensionDetails
from app.schemas.db_pension import DbPensionDetailsIn, DbPensionSummaryOut
from app.services import settings_service

# Used when the owner has no date of birth, so there is no pension date to work from. Far enough
# out that the pension is treated as not yet in payment.
_UNKNOWN_START_YEARS = 100


def _owner(account: Account):
    return account.owners[0].person if account.owners else None


def pension_start_date(account: Account) -> date | None:
    details = account.db_pension_details
    person = _owner(account)
    if details is None or person is None or person.date_of_birth is None:
        return None
    return add_months(person.date_of_birth, details.normal_pension_age * 12)


def terms_for(account: Account) -> engine.DbPensionTerms:
    details = account.db_pension_details
    if details is None:
        raise DomainError("validation", "This pension has no scheme details yet", field="db_pension")
    start = pension_start_date(account) or add_months(details.accrued_as_of, _UNKNOWN_START_YEARS * 12)
    person = _owner(account)
    leave: date | None = None
    if not details.is_active_member:
        leave = details.accrued_as_of
    elif person is not None and person.date_of_birth is not None:
        # Stops building up at retirement if that comes before the scheme's pension age.
        leave = add_months(person.date_of_birth, person.retirement_age * 12)
    return engine.DbPensionTerms(
        accrued_annual_pension=details.accrued_annual_pension_gbp,
        accrued_as_of=details.accrued_as_of,
        pension_start=start,
        accrual_rate=details.accrual_rate,
        revaluation_above_cpi=details.revaluation_above_cpi,
        pensionable_salary=details.pensionable_salary_gbp if details.is_active_member else 0.0,
        salary_growth_rate=details.salary_growth_rate,
        leave_service=leave,
        accrued_lump_sum=details.accrued_lump_sum_gbp,
        capitalisation_factor=details.capitalisation_factor,
    )


def cpi(db: Session) -> float:
    return float(settings_service.get_all(db).get("inflation_rate", 0.025))


def value_on(db: Session, account: Account, on: date) -> float:
    return engine.capitalised_value(terms_for(account), on, cpi(db))


def summary(db: Session, account: Account) -> DbPensionSummaryOut:
    on = date_today()
    rate = cpi(db)
    terms = terms_for(account)
    pension, lump = engine.benefits_on(terms, on, rate)
    start = pension_start_date(account)
    at_start = engine.pension_at_start(terms, rate) if start is not None else None
    return DbPensionSummaryOut(
        annual_pension_today_gbp=round(pension, 2),
        lump_sum_today_gbp=round(lump, 2),
        capitalised_value_gbp=round(engine.capitalised_value(terms, on, rate), 2),
        pension_start_date=start,
        annual_pension_at_start_gbp=round(at_start[0], 2) if at_start else None,
        annual_pension_at_start_today_money_gbp=(
            round(deflate(at_start[0], rate, years_between(on, start)), 2) if at_start and start else None
        ),
        lump_sum_at_start_gbp=round(at_start[1], 2) if at_start else None,
    )


def upsert(db: Session, account: Account, payload: DbPensionDetailsIn) -> DbPensionDetails:
    details = account.db_pension_details
    if details is None:
        details = DbPensionDetails(account_id=account.id)
        db.add(details)
        account.db_pension_details = details
    for key, value in payload.model_dump().items():
        setattr(details, key, value)
    return details
