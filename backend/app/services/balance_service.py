from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import ValuationMethod
from app.core.errors import NotFoundError
from app.models.accounts import Account, AccountOwner
from app.models.balances import BalanceEntry
from app.schemas.balance import BalanceEntryIn, BalanceEntryUpdate, BulkBalanceEntry, QuickUpdateRow
from app.services import valuation_service

QUICK_UPDATE_METHODS = (ValuationMethod.balance, ValuationMethod.model, ValuationMethod.amortising)


def list_balances(db: Session, account_id: int) -> list[BalanceEntry]:
    return list(
        db.scalars(
            select(BalanceEntry)
            .where(BalanceEntry.account_id == account_id)
            .order_by(BalanceEntry.date.desc())
        ).all()
    )


def upsert_balance(db: Session, account: Account, payload: BalanceEntryIn) -> BalanceEntry:
    entry = db.scalars(
        select(BalanceEntry).where(
            BalanceEntry.account_id == account.id, BalanceEntry.date == payload.date
        )
    ).first()
    if entry is None:
        entry = BalanceEntry(account_id=account.id, date=payload.date)
        db.add(entry)
    entry.balance_gbp = round(payload.balance_gbp, 2)
    entry.source = payload.source
    entry.notes = payload.notes
    db.commit()
    db.refresh(entry)

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account.id, entry.date)
    projection_service.bump_data_version()
    return entry


def get_balance_entry(db: Session, entry_id: int) -> BalanceEntry:
    entry = db.get(BalanceEntry, entry_id)
    if entry is None:
        raise NotFoundError(f"Balance entry {entry_id} not found")
    return entry


def update_balance_entry(db: Session, entry: BalanceEntry, payload: BalanceEntryUpdate) -> BalanceEntry:
    account_id = entry.account_id
    earliest = entry.date
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, round(value, 2) if field == "balance_gbp" else value)
    earliest = min(earliest, entry.date)
    db.commit()
    db.refresh(entry)

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account_id, earliest)
    projection_service.bump_data_version()
    return entry


def delete_balance_entry(db: Session, entry: BalanceEntry) -> None:
    account_id = entry.account_id
    entry_date = entry.date
    db.delete(entry)
    db.commit()

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account_id, entry_date)
    projection_service.bump_data_version()


def bulk_save(db: Session, entries: list[BulkBalanceEntry]) -> int:
    saved = 0
    for item in entries:
        account = db.get(Account, item.account_id)
        if account is None:
            raise NotFoundError(f"Account {item.account_id} not found")
        existing = db.scalars(
            select(BalanceEntry).where(
                BalanceEntry.account_id == item.account_id, BalanceEntry.date == item.date
            )
        ).first()
        if existing is None:
            existing = BalanceEntry(account_id=item.account_id, date=item.date)
            db.add(existing)
        existing.balance_gbp = round(item.balance_gbp, 2)
        existing.source = item.source
        saved += 1
    db.commit()

    from app.services import projection_service, snapshot_service

    for item in entries:
        snapshot_service.request_rebuild(item.account_id, item.date)
    if entries:
        projection_service.bump_data_version()
    return saved


def quick_update_rows(db: Session, person_id: int | None = None) -> list[QuickUpdateRow]:
    query = select(Account).where(
        Account.is_archived.is_(False), Account.valuation_method.in_(QUICK_UPDATE_METHODS)
    )
    if person_id is not None:
        query = query.join(AccountOwner).where(AccountOwner.person_id == person_id)
    accounts = db.scalars(query.order_by(Account.sort_order, Account.name)).unique().all()

    on = today()
    rows: list[QuickUpdateRow] = []
    for account in accounts:
        entry = valuation_service.latest_balance_entry(db, account.id, on)
        rows.append(
            QuickUpdateRow(
                account_id=account.id,
                name=account.name,
                category=account.category.value,
                owners=[o.person.name for o in account.owners],
                valuation_method=account.valuation_method.value,
                last_date=entry.date if entry else None,
                last_balance_gbp=entry.balance_gbp if entry else None,
                modelled_value_gbp=valuation_service.modelled_value_gbp(db, account, on),
                days_since=valuation_service.days_since_last_entry(db, account, on),
                staleness=valuation_service.staleness(db, account, on),
            )
        )
    return rows
