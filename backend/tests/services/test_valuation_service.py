from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.enums import Category, RateType, ValuationMethod, Wrapper
from app.models.balances import BalanceEntry
from app.models.people import Person
from app.schemas.account import AccountCreate, GrowthModelIn, InitialBalanceIn, OwnerShareIn
from app.schemas.loan import LoanDetailsCreate, RatePeriodIn
from app.services import account_service, valuation_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def test_balance_valuation_uses_latest_entry_on_or_before(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Cash",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=100.0),
        ),
    )
    db.add(BalanceEntry(account_id=account.id, date=date(2026, 6, 1), balance_gbp=150.0))
    db.commit()

    valuation = valuation_service.value_account(db, account, date(2026, 7, 1), live=True)
    assert valuation.value_gbp == 150.0

    earlier = valuation_service.value_account(db, account, date(2026, 3, 1), live=True)
    assert earlier.value_gbp == 100.0


def test_model_valuation_depreciates_a_car_by_15pct_over_one_year(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Car",
            category=Category.other_asset,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.model,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2025, 9, 15), balance_gbp=20000.0),
            growth_model=GrowthModelIn(annual_rate=-0.15, method="compound"),
        ),
    )

    valuation = valuation_service.value_account(db, account, date(2026, 9, 15), live=True)
    assert abs(valuation.value_gbp - 17000.0) < 10
    assert valuation.is_estimated is True


def test_amortising_valuation_falls_back_to_the_loans_start_date_and_amount(db: Session):
    """A mortgage created via the Property page's "Add mortgage" flow (or any amortising
    account) has no BalanceEntry until a statement is added by hand — the anchor must fall back
    to loan.start_date / original_amount_gbp (matching loan_service.get_anchor, used by
    /schedule) so the account's snapshot/history isn't stuck at zero. Regression for the bug
    where _value_amortising read BalanceEntry directly and ignored that fallback."""
    james = _person(db)
    start = date(2024, 9, 1)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Mortgage",
            category=Category.mortgage,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.amortising,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            loan=LoanDetailsCreate(
                original_amount_gbp=200000.0,
                start_date=start,
                maturity_date=date(2049, 9, 1),
                fallback_rate=0.045,
                rate_periods=[
                    RatePeriodIn(
                        start_date=start, end_date=None, annual_rate=0.045, rate_type=RateType.fixed
                    )
                ],
            ),
        ),
    )

    # On/before the loan's own start date the balance is exactly the original amount.
    at_start = valuation_service.value_account(db, account, start, live=False)
    assert at_start.value_gbp == -200000.0

    # Two years in (still well before creation "today"), the balance has amortised down —
    # this is the historical trajectory the Property page chart plots.
    two_years_in = valuation_service.value_account(db, account, date(2026, 9, 1), live=False)
    assert two_years_in.value_gbp < -180000.0
    assert two_years_in.value_gbp > -200000.0


def test_liability_value_is_signed_negative(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Credit card",
            category=Category.credit_card,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 15), balance_gbp=500.0),
        ),
    )
    valuation = valuation_service.value_account(db, account, date(2026, 9, 15), live=True)
    assert valuation.value_gbp == -500.0


def test_scoped_value_applies_owner_share(db: Session):
    james = _person(db, "James")
    sam = _person(db, "Sam")
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Joint",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=0.5), OwnerShareIn(person_id=sam.id, share=0.5)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 15), balance_gbp=2000.0),
        ),
    )
    assert valuation_service.scoped_value(2000.0, account, {james.id}) == 1000.0
    assert valuation_service.scoped_value(2000.0, account, {james.id, sam.id}) == 2000.0


def test_staleness_thresholds(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Nationwide Flex",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=100.0),
        ),
    )
    assert valuation_service.staleness(db, account, date(2026, 1, 10)) == "ok"
    assert valuation_service.staleness(db, account, date(2026, 2, 10)) == "warn"  # 40 days
    assert valuation_service.staleness(db, account, date(2026, 5, 1)) == "alert"  # 120 days


def test_days_since_update_counts_from_the_last_entry(db: Session):
    """Issue #27: the account list needs the age, not only the staleness level."""
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Nationwide Flex",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            initial_balance=InitialBalanceIn(date=date(2026, 1, 1), balance_gbp=100.0),
        ),
    )
    empty = account_service.create_account(
        db,
        AccountCreate(
            name="New saver",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    assert valuation_service.days_since_update(db, account, date(2026, 5, 1)) == 120
    assert valuation_service.days_since_update(db, empty, date(2026, 5, 1)) is None


def test_days_since_update_for_holdings_is_the_oldest_held_price(db: Session):
    from app.core.enums import PriceSource
    from app.models.instruments import Instrument
    from app.models.prices import InstrumentPrice
    from app.services import ledger_service

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
    for symbol, last in (("VWRL.L", date(2026, 4, 28)), ("VUSA.L", date(2026, 4, 17))):
        instrument = Instrument(symbol=symbol, name=symbol, quote_currency="GBP", price_source=PriceSource.yahoo)
        db.add(instrument)
        db.commit()
        db.add(
            InstrumentPrice(
                instrument_id=instrument.id, date=last, close_native=10, close_gbp=10, source=PriceSource.yahoo
            )
        )
        db.commit()
        ledger_service.set_position_target(db, account.id, instrument.id, 5, 10, as_of=date(2026, 1, 1))

    assert valuation_service.days_since_update(db, account, date(2026, 5, 1)) == 14
