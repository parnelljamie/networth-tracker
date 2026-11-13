from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import Category, PriceSource, ValuationMethod, Wrapper
from app.models.instruments import Instrument
from app.models.people import Person
from app.models.prices import InstrumentPrice
from app.schemas.account import AccountCreate, OwnerShareIn
from app.services import account_service, ledger_service, networth_service, price_service
from tests.fakes import FakeProvider


def _person(db: Session) -> Person:
    person = Person(name="James")
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _holdings_account(db: Session, person: Person, name: str, wrapper: Wrapper = Wrapper.isa) -> int:
    return account_service.create_account(
        db,
        AccountCreate(
            name=name,
            category=Category.investment,
            wrapper=wrapper,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=person.id, share=1.0)],
        ),
    ).id


def _instrument(db: Session, symbol: str) -> Instrument:
    instrument = Instrument(symbol=symbol, name=symbol, quote_currency="GBP", price_source=PriceSource.yahoo)
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    return instrument


def test_holdings_account_with_old_prices_is_listed_as_stale(db: Session):
    james = _person(db)
    account_id = _holdings_account(db, james, "ISA")
    instrument = _instrument(db, "OLD.L")
    ledger_service.set_position_target(db, account_id, instrument.id, 10, 1.0)
    db.add(
        InstrumentPrice(
            instrument_id=instrument.id,
            date=today() - timedelta(days=30),
            close_native=1.0,
            close_gbp=1.0,
            source=PriceSource.yahoo,
        )
    )
    db.commit()

    current = networth_service.get_current(db)

    assert [(s.account_id, s.days_since, s.staleness) for s in current.freshness.stale_accounts] == [
        (account_id, 30, "alert")
    ]


def test_an_instrument_held_in_two_accounts_is_one_mover(db: Session):
    james = _person(db)
    isa = _holdings_account(db, james, "ISA")
    gia = _holdings_account(db, james, "GIA", Wrapper.gia)
    instrument = _instrument(db, "VWRP.L")
    ledger_service.set_position_target(db, isa, instrument.id, 10, 100.0)
    ledger_service.set_position_target(db, gia, instrument.id, 30, 100.0)
    provider = FakeProvider()
    provider.set_quote("VWRP.L", last=110.0, prev_close=100.0, bar_date=today())
    price_service.refresh_quotes(db, provider, force=True)

    current = networth_service.get_current(db)

    assert current.top_movers == [
        {
            "instrument_id": instrument.id,
            "symbol": "VWRP.L",
            "name": "VWRP.L",
            "day_change_gbp": 400.0,
            "day_change_pct": 0.1,
        }
    ]
