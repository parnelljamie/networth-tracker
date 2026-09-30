from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.enums import (
    Category,
    ContributionSource,
    PriceSource,
    TxnStatus,
    TxnType,
    ValuationMethod,
    Wrapper,
)
from app.models.instruments import Instrument
from app.models.people import Person
from app.models.snapshots import AccountSnapshot
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.services import account_service, attribution_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _snapshot(db: Session, account_id: int, on: date, value_gbp: float) -> None:
    db.add(AccountSnapshot(account_id=account_id, date=on, value_gbp=value_gbp, is_estimated=False))
    db.commit()


def test_attribution_buckets_sum_to_net_worth_change(db: Session):
    james = _person(db)
    start, end = date(2026, 8, 1), date(2026, 9, 1)

    # Holdings account: deposits £500, market moves the rest.
    holdings = account_service.create_account(
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
        price_source=PriceSource.manual, manual_price_gbp=100.0,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    db.add(
        Transaction(
            account_id=holdings.id,
            date=date(2026, 8, 15),
            type=TxnType.DEPOSIT,
            amount_gbp=500.0,
            status=TxnStatus.confirmed,
            contribution_source=ContributionSource.personal,
        )
    )
    db.commit()
    _snapshot(db, holdings.id, start, 1000.0)
    _snapshot(db, holdings.id, end, 1700.0)  # +500 contributions, +200 market

    # Cash account: pure balance movement counted as contributions.
    cash = account_service.create_account(
        db,
        AccountCreate(
            name="Savings",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=2000.0),
        ),
    )
    _snapshot(db, cash.id, start, 2000.0)
    _snapshot(db, cash.id, end, 2300.0)  # +300 contributions

    # Mortgage: liability, paying down debt is a positive delta to net worth. Uses the
    # `balance` valuation method (not `amortising`) purely to keep this test's fixture simple —
    # attribution's liability bucket keys off `account.category`, not the valuation method.
    mortgage = account_service.create_account(
        db,
        AccountCreate(
            name="Mortgage",
            category=Category.mortgage,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2020, 1, 1), balance_gbp=150000.0),
        ),
    )
    _snapshot(db, mortgage.id, start, -150000.0)
    _snapshot(db, mortgage.id, end, -149400.0)  # +600 paid down

    result = attribution_service.attribution(db, start, end)

    assert round(result.contributions_gbp, 2) == 800.0  # 500 holdings + 300 cash
    assert round(result.market_gbp, 2) == 200.0
    assert round(result.mortgage_paid_gbp, 2) == 600.0
    assert round(result.revaluation_gbp, 2) == 0.0

    computed_total = (
        result.contributions_gbp
        + result.market_gbp
        + result.mortgage_paid_gbp
        + result.revaluation_gbp
        + result.other_gbp
    )
    net_worth_change = result.end_total_gbp - result.start_total_gbp
    assert round(computed_total, 2) == round(net_worth_change, 2)
    assert round(net_worth_change, 2) == 1600.0  # 700 + 300 + 600


def test_share_transfer_in_counts_as_contribution_at_cost(db: Session):
    james = _person(db)
    start, end = date(2026, 8, 1), date(2026, 9, 1)
    isa = account_service.create_account(
        db,
        AccountCreate(
            name="New ISA", category=Category.investment, wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings, owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    instrument = Instrument(
        symbol="VUKE.L", name="Vanguard FTSE 100", quote_currency="GBP",
        price_source=PriceSource.manual, manual_price_gbp=55.0,
    )
    db.add(instrument)
    db.commit()
    # An ISA transfer in specie: 99 units arrive with no cash, at their £5,332.14 cost.
    db.add(
        Transaction(
            account_id=isa.id, instrument_id=instrument.id, date=date(2026, 8, 26), type=TxnType.TRANSFER_IN,
            units=99, amount_gbp=0.0, cost_basis_gbp=5332.14, status=TxnStatus.confirmed,
        )
    )
    db.commit()
    _snapshot(db, isa.id, start, 0.0)
    _snapshot(db, isa.id, end, 5445.0)

    result = attribution_service.attribution(db, start, end)
    assert round(result.contributions_gbp, 2) == 5332.14
    assert round(result.market_gbp, 2) == 112.86
