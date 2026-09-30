from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import Category, PriceSource, TxnStatus, TxnType, ValuationMethod, Wrapper
from app.models.instruments import Instrument
from app.models.people import Person
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.services import account_service, insights_service, ledger_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _cash_account(db: Session, owner_id: int, provider: str, balance: float) -> object:
    return account_service.create_account(
        db,
        AccountCreate(
            name=f"{provider} Savings",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            provider=provider,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=balance),
        ),
    )


def test_deposit_protection_flags_provider_over_limit(db: Session):
    james = _person(db)
    _cash_account(db, james.id, "Big Bank", 80000.0)
    _cash_account(db, james.id, "Big Bank", 60000.0)  # same provider, combined > 120k limit
    _cash_account(db, james.id, "Other Bank", 5000.0)

    result = insights_service.deposit_protection(db)
    by_provider = {e.provider: e for e in result.entries}

    assert by_provider["Big Bank"].total_gbp == 140000.0
    assert by_provider["Big Bank"].exceeded is True
    assert by_provider["Other Bank"].exceeded is False


def test_xirr_computable_for_a_simple_deposit_and_current_value(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="ISA",
            category=Category.investment,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    instrument = Instrument(
        symbol="VUSA.L", name="Vanguard S&P 500", quote_currency="GBP",
        price_source=PriceSource.manual, manual_price_gbp=110.0,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)

    db.add(
        Transaction(
            account_id=account.id,
            date=date(2025, 9, 16),
            type=TxnType.DEPOSIT,
            amount_gbp=1000.0,
            status=TxnStatus.confirmed,
        )
    )
    db.add(
        Transaction(
            account_id=account.id,
            date=date(2025, 9, 16),
            instrument_id=instrument.id,
            type=TxnType.BUY,
            units=10.0,
            price_native=100.0,
            amount_gbp=-1000.0,
            status=TxnStatus.confirmed,
        )
    )
    db.commit()

    # Live valuation reads the `positions` cache, not transactions directly (CONTRIBUTING.md convention 11:
    # "positions are derived from transactions... never write to positions directly; it is a
    # cache") -- the transactions above were inserted directly, so rebuild it explicitly (mirrors
    # what `ledger_service.create_transaction` does for us normally).
    ledger_service.rebuild_positions(db, account.id)
    db.commit()

    with freeze_time("2026-09-16"):
        result = insights_service.account_xirr(db, account)

    assert result is not None
    assert result > 0  # value grew from 1000 -> 1100 over ~1 year


def test_xirr_none_when_flows_are_all_one_sign(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="ISA",
            category=Category.investment,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    # No transactions at all: only "today's value" (0) would be added as a flow, which alone
    # can't produce a rate -> xirr() must return None per app/engine/returns.py's own contract.
    result = insights_service.account_xirr(db, account)
    assert result is None


def test_xirr_none_for_non_holdings_account(db: Session):
    james = _person(db)
    account = _cash_account(db, james.id, "Bank", 1000.0)
    assert insights_service.account_xirr(db, account) is None


def _isa_with_price(db: Session, price_gbp: float) -> tuple[object, Instrument]:
    account = account_service.create_account(
        db,
        AccountCreate(
            name="ISA", category=Category.investment, wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings, owners=[OwnerShareIn(person_id=_person(db).id, share=1.0)],
        ),
    )
    instrument = Instrument(
        symbol="VUKG.L", name="FTSE 100", quote_currency="GBP", price_source=PriceSource.manual,
        manual_price_gbp=price_gbp,
    )
    db.add(instrument)
    db.commit()
    return account, instrument


def test_shares_transferred_in_count_as_money_in_and_short_histories_are_not_annualised(db: Session):
    account, instrument = _isa_with_price(db, 110.0)
    # An ISA transfer: 10 shares worth £1,000 arrive with no cash; they're now worth £1,100.
    db.add(Transaction(account_id=account.id, instrument_id=instrument.id, date=date(2026, 8, 17),
                       type=TxnType.TRANSFER_IN, units=10, amount_gbp=0.0, cost_basis_gbp=1000.0,
                       status=TxnStatus.confirmed))
    db.commit()
    ledger_service.rebuild_positions(db, account.id)
    db.commit()

    with freeze_time("2026-09-16"):
        result = insights_service.account_return(db, account)

    assert result.annualised is False and result.since == date(2026, 8, 17)
    assert abs(result.rate - 0.10) < 1e-6  # +10% since the transfer, not ~+220% "a year"


def test_a_year_or_more_of_history_is_annualised(db: Session):
    account, instrument = _isa_with_price(db, 110.0)
    db.add(Transaction(account_id=account.id, instrument_id=instrument.id, date=date(2024, 9, 16),
                       type=TxnType.TRANSFER_IN, units=10, amount_gbp=0.0, cost_basis_gbp=1000.0,
                       status=TxnStatus.confirmed))
    db.commit()
    ledger_service.rebuild_positions(db, account.id)
    db.commit()

    with freeze_time("2026-09-16"):
        result = insights_service.account_return(db, account)

    assert result.annualised is True
    assert abs(result.rate - (1.1 ** 0.5 - 1)) < 1e-3  # +10% over two years
