from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Category, PriceSource, ValuationMethod, Wrapper
from app.core.errors import DomainError
from app.models.instruments import Instrument
from app.models.people import Person
from app.schemas.account import AccountCreate, OwnerShareIn
from app.schemas.transaction import TransactionCreate
from app.services import account_service, holdings_service, ledger_service


def _setup(db: Session) -> tuple[int, int]:
    person = Person(name="James")
    db.add(person)
    db.commit()
    db.refresh(person)

    account = account_service.create_account(
        db,
        AccountCreate(
            name="ISA",
            category=Category.investment,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=person.id, share=1.0)],
        ),
    )
    instrument = Instrument(
        symbol="MANUAL:X",
        name="X",
        quote_currency="GBP",
        price_source=PriceSource.manual,
        manual_price_gbp=10.0,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    return account.id, instrument.id


def test_first_edit_creates_single_opening_balance(db: Session):
    account_id, instrument_id = _setup(db)

    ledger_service.set_position_target(db, account_id, instrument_id, units=100, avg_cost_gbp=8.0)
    rows, total = ledger_service.list_transactions(db, account_id)
    assert total == 1
    assert rows[0].type == "OPENING_BALANCE"
    assert rows[0].units == 100

    ledger_service.set_position_target(db, account_id, instrument_id, units=110, avg_cost_gbp=8.0)
    rows, total = ledger_service.list_transactions(db, account_id)
    assert total == 1
    assert rows[0].type == "OPENING_BALANCE"
    assert rows[0].units == 110


def test_edit_after_buy_writes_adjustment(db: Session):
    account_id, instrument_id = _setup(db)

    ledger_service.create_transaction(
        db,
        account_id,
        TransactionCreate(date=date(2026, 9, 1), type="BUY", instrument_id=instrument_id, units=50, amount_gbp=-500),
    )
    ledger_service.set_position_target(db, account_id, instrument_id, units=50, avg_cost_gbp=15.0)

    rows, total = ledger_service.list_transactions(db, account_id)
    assert total == 2
    types = {r.type for r in rows}
    assert types == {"BUY", "ADJUSTMENT"}

    account = account_service.get_account(db, account_id)
    holdings = holdings_service.build_holdings(db, account)
    position = holdings.positions[0]
    assert position.units == 50
    assert position.cost_basis_gbp == 750.0
    assert position.avg_cost_gbp == 15.0


def test_oversell_is_rejected(db: Session):
    account_id, instrument_id = _setup(db)
    ledger_service.create_transaction(
        db,
        account_id,
        TransactionCreate(date=date(2026, 9, 1), type="BUY", instrument_id=instrument_id, units=10, amount_gbp=-100),
    )
    with pytest.raises(DomainError):
        ledger_service.create_transaction(
            db,
            account_id,
            TransactionCreate(
                date=date(2026, 9, 2), type="SELL", instrument_id=instrument_id, units=20, amount_gbp=200
            ),
        )


def test_holdings_totals(db: Session):
    account_id, instrument_id = _setup(db)
    ledger_service.set_position_target(db, account_id, instrument_id, units=10, avg_cost_gbp=10.0)
    account = account_service.get_account(db, account_id)
    holdings = holdings_service.build_holdings(db, account)

    assert holdings.totals.value_gbp == 100.0  # 10 units at manual price 10.0
    assert holdings.totals.cost_basis_gbp == 100.0
    assert holdings.totals.gain_gbp == 0.0


def test_remove_holding_with_only_an_opening_balance_deletes_it(db: Session):
    # An instrument-linked OPENING_BALANCE can't have units = 0 (engine.ledger.validate_txn), so
    # zeroing the one-and-only row for a position removes it rather than writing an invalid one.
    account_id, instrument_id = _setup(db)
    ledger_service.set_position_target(db, account_id, instrument_id, units=10, avg_cost_gbp=10.0)

    ledger_service.remove_holding(db, account_id, instrument_id)

    account = account_service.get_account(db, account_id)
    holdings = holdings_service.build_holdings(db, account)
    assert holdings.positions == []
    _, total = ledger_service.list_transactions(db, account_id)
    assert total == 0


def test_remove_holding_with_real_history_keeps_it_and_adds_an_adjustment(db: Session):
    account_id, instrument_id = _setup(db)
    ledger_service.create_transaction(
        db,
        account_id,
        TransactionCreate(date=date(2026, 9, 1), type="BUY", instrument_id=instrument_id, units=10, amount_gbp=-100),
    )

    ledger_service.remove_holding(db, account_id, instrument_id)

    account = account_service.get_account(db, account_id)
    holdings = holdings_service.build_holdings(db, account)
    assert holdings.positions == []
    rows, total = ledger_service.list_transactions(db, account_id)
    assert total == 2
    assert {r.type for r in rows} == {"BUY", "ADJUSTMENT"}
