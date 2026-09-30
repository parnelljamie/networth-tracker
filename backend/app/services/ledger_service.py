from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import TxnSource, TxnStatus, TxnType
from app.core.errors import DomainError, NotFoundError
from app.engine import ledger
from app.models.accounts import Account
from app.models.positions import Position
from app.models.transactions import Transaction
from app.schemas.transaction import ConfirmItem, TransactionCreate, TransactionUpdate


def confirmed_txns(db: Session, account_id: int) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction).where(
                Transaction.account_id == account_id, Transaction.status == TxnStatus.confirmed
            )
        ).all()
    )


def to_engine_txn(row: Transaction) -> ledger.Txn:
    return ledger.Txn(
        date=row.date,
        type=row.type.value if hasattr(row.type, "value") else row.type,
        instrument_id=row.instrument_id,
        units=row.units,
        amount_gbp=row.amount_gbp,
        cost_basis_gbp=row.cost_basis_gbp,
        split_ratio=row.split_ratio,
        id=row.id if row.id is not None else 0,
    )


def _validate_against_ledger(
    db: Session, account_id: int, candidate: Transaction, exclude_id: int | None = None
) -> None:
    engine_txn = to_engine_txn(candidate)
    try:
        ledger.validate_txn(engine_txn)
        others = [r for r in confirmed_txns(db, account_id) if r.id != exclude_id]
        ledger.replay([to_engine_txn(r) for r in others] + [engine_txn], strict=True)
    except ledger.LedgerError as e:
        raise DomainError("validation", str(e), field=None) from e


def rebuild_positions(db: Session, account_id: int) -> list[str]:
    """Replay confirmed transactions and rewrite the positions cache + cash_balance_gbp.

    Call inside the same DB transaction as any create/update/delete/confirm of a transaction.
    """
    rows = confirmed_txns(db, account_id)
    state = ledger.replay([to_engine_txn(r) for r in rows], strict=False)

    # "evaluate" drops any loaded Position rows from the session too, so re-adding the same
    # (account, instrument) keys below doesn't clash with stale objects in the identity map.
    db.query(Position).filter(Position.account_id == account_id).delete(synchronize_session="evaluate")
    for instrument_id, pos in state.held().items():
        db.add(
            Position(
                account_id=account_id,
                instrument_id=instrument_id,
                units=round(pos.units, 8),
                cost_basis_gbp=round(pos.cost_gbp, 2),
                realised_gain_gbp=round(pos.realised_gain_gbp, 2),
                first_date=pos.first_date,
            )
        )

    account = db.get(Account, account_id)
    if account is not None:
        account.cash_balance_gbp = round(state.cash_gbp, 2)

    db.flush()

    from app.services import projection_service

    projection_service.bump_data_version()
    return state.warnings


def validate_new(db: Session, account_id: int, txn: Transaction) -> None:
    _validate_against_ledger(db, account_id, txn, exclude_id=None)


def get_transaction(db: Session, txn_id: int) -> Transaction:
    txn = db.get(Transaction, txn_id)
    if txn is None:
        raise NotFoundError(f"Transaction {txn_id} not found")
    return txn


def list_transactions(
    db: Session,
    account_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    txn_type: TxnType | None = None,
    status: TxnStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    query = select(Transaction).where(Transaction.account_id == account_id)
    if date_from is not None:
        query = query.where(Transaction.date >= date_from)
    if date_to is not None:
        query = query.where(Transaction.date <= date_to)
    if txn_type is not None:
        query = query.where(Transaction.type == txn_type)
    if status is not None:
        query = query.where(Transaction.status == status)

    total = len(list(db.scalars(query).all()))
    rows = list(
        db.scalars(query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset)).all()
    )
    return rows, total


def create_transaction(db: Session, account_id: int, payload: TransactionCreate) -> Transaction:
    txn = Transaction(account_id=account_id, **payload.model_dump())
    validate_new(db, account_id, txn)
    db.add(txn)
    db.flush()
    rebuild_positions(db, account_id)
    db.commit()
    db.refresh(txn)

    from app.services import snapshot_service

    snapshot_service.request_rebuild(account_id, txn.date)
    return txn


def update_transaction(db: Session, txn: Transaction, payload: TransactionUpdate) -> Transaction:
    account_id = txn.account_id
    earliest = txn.date
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(txn, field, value)
    earliest = min(earliest, txn.date)
    if txn.status == TxnStatus.confirmed:
        _validate_against_ledger(db, account_id, txn, exclude_id=txn.id)
    db.flush()
    rebuild_positions(db, account_id)
    db.commit()
    db.refresh(txn)

    from app.services import snapshot_service

    snapshot_service.request_rebuild(account_id, earliest)
    return txn


def delete_transaction(db: Session, txn: Transaction) -> None:
    account_id = txn.account_id
    txn_date = txn.date
    db.delete(txn)
    db.flush()
    rebuild_positions(db, account_id)
    db.commit()

    from app.services import snapshot_service

    snapshot_service.request_rebuild(account_id, txn_date)


def set_position_target(
    db: Session,
    account_id: int,
    instrument_id: int,
    units: float,
    avg_cost_gbp: float,
    as_of: date | None = None,
) -> list[str]:
    """The inline "edit units / avg cost" action in the holdings table."""
    as_of = as_of or today()
    rows = confirmed_txns(db, account_id)
    instrument_rows = [r for r in rows if r.instrument_id == instrument_id]

    # An instrument-linked OPENING_BALANCE must have units > 0 (engine.ledger.validate_txn), so
    # zeroing a position that is only ever a single OPENING_BALANCE removes that row instead of
    # writing an invalid one — there is no other history for that instrument to preserve anyway.
    if len(instrument_rows) == 1 and instrument_rows[0].type == TxnType.OPENING_BALANCE:
        row = instrument_rows[0]
        if units <= 1e-9:
            db.delete(row)
        else:
            row.units = round(units, 8)
            row.cost_basis_gbp = round(units * avg_cost_gbp, 2)
    elif not instrument_rows:
        if units > 1e-9:
            db.add(
                Transaction(
                    account_id=account_id,
                    instrument_id=instrument_id,
                    date=as_of,
                    type=TxnType.OPENING_BALANCE,
                    units=round(units, 8),
                    amount_gbp=0.0,
                    cost_basis_gbp=round(units * avg_cost_gbp, 2),
                    status=TxnStatus.confirmed,
                    source=TxnSource.opening,
                )
            )
    else:
        state = ledger.replay([to_engine_txn(r) for r in rows], strict=False)
        du, dc = ledger.position_target_adjustment(state, instrument_id, units, avg_cost_gbp)
        if abs(du) > 1e-9 or abs(dc) > 0.005:
            db.add(
                Transaction(
                    account_id=account_id,
                    instrument_id=instrument_id,
                    date=as_of,
                    type=TxnType.ADJUSTMENT,
                    units=round(du, 8),
                    amount_gbp=0.0,
                    cost_basis_gbp=round(dc, 2),
                    status=TxnStatus.confirmed,
                    source=TxnSource.manual,
                )
            )

    db.flush()
    warnings = rebuild_positions(db, account_id)
    db.commit()

    from app.services import snapshot_service

    snapshot_service.request_rebuild(account_id, as_of)
    return warnings


def set_cash_target(
    db: Session, account_id: int, cash_gbp: float, as_of: date | None = None
) -> list[str]:
    as_of = as_of or today()
    rows = confirmed_txns(db, account_id)
    state = ledger.replay([to_engine_txn(r) for r in rows], strict=False)
    delta = ledger.cash_target_adjustment(state, cash_gbp)
    if abs(delta) > 0.005:
        db.add(
            Transaction(
                account_id=account_id,
                instrument_id=None,
                date=as_of,
                type=TxnType.ADJUSTMENT,
                units=0.0,
                amount_gbp=round(delta, 2),
                cost_basis_gbp=0.0,
                status=TxnStatus.confirmed,
                source=TxnSource.manual,
            )
        )
    db.flush()
    warnings = rebuild_positions(db, account_id)
    db.commit()

    from app.services import snapshot_service

    snapshot_service.request_rebuild(account_id, as_of)
    return warnings


def remove_holding(db: Session, account_id: int, instrument_id: int, as_of: date | None = None) -> list[str]:
    """DELETE /accounts/{id}/holdings/{instrument_id}: sets target units to 0, keeps history."""
    return set_position_target(db, account_id, instrument_id, units=0.0, avg_cost_gbp=0.0, as_of=as_of)


def list_pending(db: Session) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.status == TxnStatus.pending)
            .order_by(Transaction.date)
        ).all()
    )


def confirm_pending(db: Session, items: list[ConfirmItem]) -> list[Transaction]:
    affected_accounts: set[int] = set()
    confirmed: list[Transaction] = []
    for item in items:
        row = db.get(Transaction, item.id)
        if row is None or row.status != TxnStatus.pending:
            continue
        if item.units is not None:
            row.units = item.units
        if item.amount_gbp is not None:
            row.amount_gbp = item.amount_gbp
        if item.price_native is not None:
            row.price_native = item.price_native
        row.status = TxnStatus.confirmed
        affected_accounts.add(row.account_id)
        confirmed.append(row)

    db.flush()
    for account_id in affected_accounts:
        rebuild_positions(db, account_id)
    db.commit()
    for row in confirmed:
        db.refresh(row)

    from app.services import snapshot_service

    earliest_by_account: dict[int, date] = {}
    for row in confirmed:
        current = earliest_by_account.get(row.account_id)
        if current is None or row.date < current:
            earliest_by_account[row.account_id] = row.date
    for account_id, earliest in earliest_by_account.items():
        snapshot_service.request_rebuild(account_id, earliest)
    return confirmed
