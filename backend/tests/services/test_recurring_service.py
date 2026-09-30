from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import (
    Category,
    ContributionSource,
    Frequency,
    PlanKind,
    PriceSource,
    TxnStatus,
    TxnType,
    ValuationMethod,
    Wrapper,
)
from app.models.instruments import Instrument
from app.models.people import Person
from app.models.positions import Position
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.recurring import PlanAllocationIn, RecurringPlanCreate
from app.services import account_service, ledger_service, recurring_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _isa_account(db: Session, owner_id: int) -> object:
    return account_service.create_account(
        db,
        AccountCreate(
            name="ISA",
            category=Category.investment,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
        ),
    )


def _instrument(db: Session, symbol: str = "VUSA.L") -> Instrument:
    instrument = Instrument(
        symbol=symbol, name="Vanguard S&P 500", quote_currency="GBP", price_source=PriceSource.manual,
        manual_price_gbp=100.0,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    return instrument


def test_record_due_creates_deposit_and_buy_and_is_idempotent(db: Session):
    james = _person(db)
    account = _isa_account(db, james.id)
    instrument = _instrument(db, "VUSA.L")
    instrument2 = _instrument(db, "VWRL.L")

    with freeze_time("2026-09-16"):
        recurring_service.create_plan(
            db,
            account,
            RecurringPlanCreate(
                account_id=account.id,
                name="Monthly ISA",
                kind=PlanKind.contribution,
                amount_gbp=500.0,
                frequency=Frequency.monthly,
                start_date=date(2026, 8, 1),
                auto_record=True,
                allocations=[
                    PlanAllocationIn(instrument_id=instrument.id, weight=0.8),
                    PlanAllocationIn(instrument_id=instrument2.id, weight=0.2),
                ],
            ),
        )

    with freeze_time("2026-09-16"):
        touched = recurring_service.record_due(db, date(2026, 9, 16))

    assert len(touched) == 1
    txns = db.query(Transaction).filter(Transaction.account_id == account.id).all()
    # Two due dates (1 Aug, 1 Sep) x (1 DEPOSIT + 2 BUYs, no relief) = 6 rows.
    deposits = [t for t in txns if t.type == TxnType.DEPOSIT]
    buys = [t for t in txns if t.type == TxnType.BUY]
    assert len(deposits) == 2
    assert len(buys) == 4
    assert all(t.status == TxnStatus.pending for t in txns)
    buy_80 = [b for b in buys if b.instrument_id == instrument.id][0]
    assert buy_80.units == round(500 * 0.8 / 100.0, 8)

    # Positions must not be affected by pending transactions.
    positions = db.query(Position).filter(Position.account_id == account.id).all()
    assert positions == []
    db.refresh(account)
    assert account.cash_balance_gbp == 0.0

    # Running record_due again for the same date must not duplicate.
    recurring_service.record_due(db, date(2026, 9, 16))
    txns_after = db.query(Transaction).filter(Transaction.account_id == account.id).all()
    assert len(txns_after) == len(txns)


def test_tax_relief_splits_into_two_deposits(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="SIPP",
            category=Category.pension,
            wrapper=Wrapper.sipp,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )

    recurring_service.create_plan(
        db,
        account,
        RecurringPlanCreate(
            account_id=account.id,
            name="SIPP contribution",
            kind=PlanKind.contribution,
            amount_gbp=400.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 9, 1),
            tax_relief_rate=0.25,
            contribution_source=ContributionSource.personal,
            auto_record=True,
        ),
    )

    recurring_service.record_due(db, date(2026, 9, 1))

    deposits = (
        db.query(Transaction)
        .filter(Transaction.account_id == account.id, Transaction.type == TxnType.DEPOSIT)
        .all()
    )
    assert len(deposits) == 2
    by_source = {d.contribution_source: d.amount_gbp for d in deposits}
    assert by_source[ContributionSource.personal] == 400.0
    assert by_source[ContributionSource.tax_relief] == 100.0
    assert sum(by_source.values()) == 500.0


def test_pending_transactions_ignored_by_positions_until_confirmed(db: Session):
    james = _person(db)
    account = _isa_account(db, james.id)
    instrument = _instrument(db)

    recurring_service.create_plan(
        db,
        account,
        RecurringPlanCreate(
            account_id=account.id,
            name="Monthly ISA",
            kind=PlanKind.contribution,
            amount_gbp=500.0,
            frequency=Frequency.monthly,
            start_date=date(2026, 9, 1),
            auto_record=True,
            allocations=[PlanAllocationIn(instrument_id=instrument.id, weight=1.0)],
        ),
    )
    recurring_service.record_due(db, date(2026, 9, 1))

    positions_before = db.query(Position).filter(Position.account_id == account.id).all()
    assert positions_before == []

    pending = ledger_service.list_pending(db)
    assert len(pending) == 2

    from app.schemas.transaction import ConfirmItem

    ledger_service.confirm_pending(db, [ConfirmItem(id=t.id) for t in pending])

    positions_after = db.query(Position).filter(Position.account_id == account.id).all()
    assert len(positions_after) == 1
    assert positions_after[0].units == round(500.0 / 100.0, 8)


def test_allocations_only_valid_on_holdings_accounts(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Cash ISA",
            category=Category.cash,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 1), balance_gbp=1000.0),
        ),
    )
    instrument = _instrument(db)

    import pytest

    from app.core.errors import DomainError

    with pytest.raises(DomainError):
        recurring_service.create_plan(
            db,
            account,
            RecurringPlanCreate(
                account_id=account.id,
                name="Cash ISA plan",
                kind=PlanKind.contribution,
                amount_gbp=200.0,
                frequency=Frequency.monthly,
                start_date=date(2026, 9, 1),
                allocations=[PlanAllocationIn(instrument_id=instrument.id, weight=1.0)],
            ),
        )


def test_overpayment_plans_only_valid_on_loan_accounts(db: Session):
    james = _person(db)
    account = _isa_account(db, james.id)

    import pytest

    from app.core.errors import DomainError

    with pytest.raises(DomainError):
        recurring_service.create_plan(
            db,
            account,
            RecurringPlanCreate(
                account_id=account.id,
                name="Overpayment",
                kind=PlanKind.overpayment,
                amount_gbp=200.0,
                frequency=Frequency.monthly,
                start_date=date(2026, 9, 1),
            ),
        )
