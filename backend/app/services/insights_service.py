"""docs/03-domain-logic.md §9 "Deposit protection" and "XIRR" (Phase 7)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import Category, TxnStatus, TxnType, ValuationMethod
from app.engine import ledger
from app.engine.returns import xirr as engine_xirr
from app.models.accounts import Account
from app.models.people import Person
from app.models.transactions import Transaction
from app.schemas.insights import DepositProtectionEntry, DepositProtectionOut
from app.services import ledger_service, settings_service, valuation_service

UNKNOWN_PROVIDER = "Unknown provider"

# docs §9 XIRR flow sign convention: money in is negative, money out (incl. today's value) positive.
_OUTFLOW_TYPES = {TxnType.DEPOSIT, TxnType.TRANSFER_IN}
_INFLOW_TYPES = {TxnType.WITHDRAWAL, TxnType.TRANSFER_OUT}
_MONEY_EPS = 0.005


def deposit_protection(db: Session) -> DepositProtectionOut:
    """Group cash accounts by provider, attribute value to owners by share, and flag any
    person's total at one provider above `deposit_protection_limit_gbp` (docs §9: "the user
    should treat banks sharing a licence as one provider" — providers are grouped by the
    account's free-text `provider` field, so the user is responsible for naming shared-licence
    banks consistently; this service does no fuzzy matching)."""
    on = date_today()
    limit = settings_service.get(db, "deposit_protection_limit_gbp", 120000)

    accounts = list(
        db.scalars(
            select(Account).where(
                Account.is_archived.is_(False),
                Account.category == Category.cash,
                Account.valuation_method == ValuationMethod.balance,
            )
        ).all()
    )

    totals: dict[tuple[str, int], float] = {}
    for account in accounts:
        provider = account.provider or UNKNOWN_PROVIDER
        value = valuation_service.value_account(db, account, on, live=True).value_gbp
        for owner in account.owners:
            key = (provider, owner.person_id)
            totals[key] = totals.get(key, 0.0) + value * owner.share

    people = {p.id: p for p in db.scalars(select(Person)).all()}
    entries = [
        DepositProtectionEntry(
            provider=provider,
            person_id=person_id,
            person_name=people[person_id].name if person_id in people else "Unknown",
            total_gbp=round(total, 2),
            limit_gbp=limit,
            exceeded=total > limit,
        )
        for (provider, person_id), total in sorted(totals.items())
        if total > 0.005
    ]
    return DepositProtectionOut(entries=entries)


def _external_flows(db: Session, account: Account) -> list[tuple[date, float]]:
    """docs §9 XIRR flows: money in negative, money out positive. Shares transferred in or out
    with no cash (e.g. an ISA transfer from another provider) are money in/out too, at their
    value: the cost basis they arrived with, or the average cost they left at."""
    rows = sorted(
        db.scalars(
            select(Transaction).where(
                Transaction.account_id == account.id, Transaction.status == TxnStatus.confirmed
            )
        ).all(),
        key=lambda r: ledger.sort_key(ledger_service.to_engine_txn(r)),
    )
    flows: list[tuple[date, float]] = []
    for i, row in enumerate(rows):
        if row.type not in _OUTFLOW_TYPES | _INFLOW_TYPES:
            continue
        amount = abs(row.amount_gbp)
        if amount < _MONEY_EPS and row.instrument_id is not None:
            if row.type == TxnType.TRANSFER_IN:
                amount = abs(row.cost_basis_gbp)
            else:
                before = ledger.replay([ledger_service.to_engine_txn(r) for r in rows[:i]], strict=False)
                pos = before.positions.get(row.instrument_id)
                amount = pos.avg_cost_gbp * row.units if pos else 0.0
        flows.append((row.date, -amount if row.type in _OUTFLOW_TYPES else amount))
    return flows


def account_xirr(db: Session, account: Account) -> float | None:
    """docs §9 XIRR: the flows above plus today's value as a positive flow; `engine.returns.xirr()`
    does the maths (never reimplemented here)."""
    if account.valuation_method != ValuationMethod.holdings:
        return None
    flows = _external_flows(db, account)
    current_value = valuation_service.value_account(db, account, date_today(), live=True).value_gbp
    return engine_xirr([*flows, (date_today(), current_value)])


@dataclass
class AccountReturn:
    rate: float | None
    annualised: bool
    since: date | None


def account_return(db: Session, account: Account) -> AccountReturn:
    """The money-weighted return to show. Under a year of history it isn't annualised (the GIPS
    convention): a few weeks' gain scaled up to a year reads as nonsense, so it's the return since
    the first payment in, `(1 + xirr) ^ (days / 365) - 1`."""
    rate = account_xirr(db, account)
    flows = _external_flows(db, account) if account.valuation_method == ValuationMethod.holdings else []
    since = min((d for d, _ in flows), default=None)
    if rate is None or since is None:
        return AccountReturn(rate=rate, annualised=True, since=since)
    days = (date_today() - since).days
    if days < 365:
        return AccountReturn(rate=(1 + rate) ** (days / 365) - 1, annualised=False, since=since)
    return AccountReturn(rate=rate, annualised=True, since=since)
