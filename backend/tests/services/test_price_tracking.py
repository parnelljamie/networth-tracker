"""A manual instrument following a Yahoo instrument between its own stated prices (e.g. pension
fund units priced from statements, moved daily by the listed share class of the same fund)."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import Category, PriceSource, TxnStatus, TxnType, ValuationMethod, Wrapper
from app.core.errors import DomainError
from app.models.instruments import Instrument
from app.models.people import Person
from app.models.prices import InstrumentPrice
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, OwnerShareIn
from app.schemas.instrument import InstrumentUpdate
from app.services import account_service, instrument_service, ledger_service, price_service

STATEMENT = date(2026, 8, 31)


def _instrument(db: Session, symbol: str, source: PriceSource, **kwargs) -> Instrument:
    instrument = Instrument(symbol=symbol, name=symbol, quote_currency="GBP", price_source=source, **kwargs)
    db.add(instrument)
    db.commit()
    return instrument


def _price(db: Session, instrument: Instrument, on: date, close: float) -> None:
    db.add(InstrumentPrice(instrument_id=instrument.id, date=on, close_native=close, close_gbp=close,
                           source=instrument.price_source))
    db.commit()


@pytest.fixture
def pension(db: Session) -> tuple[Instrument, Instrument]:
    """Royal London units at £9.60 on the statement; the listed X1 class at £3.50 that day."""
    x1 = _instrument(db, "0P0001A8X7.L", PriceSource.yahoo)
    fund = _instrument(db, "MANUAL:PEN-BR-US", PriceSource.manual, manual_price_gbp=9.60,
                       manual_price_date=STATEMENT)
    _price(db, x1, STATEMENT, 3.50)
    _price(db, x1, date(2026, 9, 10), 3.85)  # +10%
    return fund, x1


def test_untracked_manual_price_stays_flat(db: Session, pension):
    fund, _x1 = pension
    assert price_service.price_gbp(db, fund, date(2026, 9, 10), live=False).price_gbp == pytest.approx(9.60)


def test_tracked_price_follows_the_move_since_the_statement(db: Session, pension):
    fund, x1 = pension
    instrument_service.update_instrument(db, fund, InstrumentUpdate(tracks_instrument_id=x1.id))

    assert price_service.price_gbp(db, fund, STATEMENT, live=False).price_gbp == pytest.approx(9.60)
    result = price_service.price_gbp(db, fund, date(2026, 9, 10), live=False)
    assert result.price_gbp == pytest.approx(9.60 * 1.1)
    assert not result.is_stale

    # A newer statement price resets the ratio: moves are measured from it.
    _price(db, fund, date(2026, 9, 30), 10.0)
    _price(db, x1, date(2026, 9, 30), 3.90)
    _price(db, x1, date(2026, 10, 5), 3.51)  # -10%
    assert price_service.price_gbp(db, fund, date(2026, 9, 30), live=False).price_gbp == pytest.approx(10.0)
    assert price_service.price_gbp(db, fund, date(2026, 10, 5), live=False).price_gbp == pytest.approx(9.0)


@freeze_time("2026-09-11 15:00:00")
def test_tracked_instrument_uses_the_live_quote_and_its_day_change(db: Session, pension):
    fund, x1 = pension
    fund.tracks_instrument_id = x1.id
    x1.last_price_gbp, x1.prev_close_gbp = 4.20, 3.85  # today's quote, not yet a stored row
    x1.last_price_at = datetime(2026, 9, 11, 14, 0)
    db.commit()
    today = date(2026, 9, 11)

    assert price_service.price_gbp(db, fund, today, live=True).price_gbp == pytest.approx(9.60 * 1.2)
    # 100 units, price 11.52 today, the tracked fund up 4.20/3.85: yesterday's value was 10.56.
    assert price_service.day_change_contribution(fund, 100, today, db) == pytest.approx(100 * (11.52 - 10.56))
    assert price_service.day_change_contribution(fund, 100, today) == 0.0  # no db: as before


def test_held_tracked_instruments_are_refreshed(db: Session, pension):
    fund, x1 = pension
    person = Person(name="James")
    db.add(person)
    db.commit()
    account = account_service.create_account(
        db,
        AccountCreate(name="Pension", category=Category.pension, wrapper=Wrapper.sipp,
                      valuation_method=ValuationMethod.holdings, owners=[OwnerShareIn(person_id=person.id, share=1.0)]),
    )
    db.add(Transaction(account_id=account.id, instrument_id=fund.id, date=STATEMENT, type=TxnType.OPENING_BALANCE,
                       units=100, amount_gbp=0.0, cost_basis_gbp=900, status=TxnStatus.confirmed))
    db.commit()
    ledger_service.rebuild_positions(db, account.id)
    assert price_service.held_yahoo_instruments(db) == []

    fund.tracks_instrument_id = x1.id
    db.commit()
    assert [i.id for i in price_service.held_yahoo_instruments(db)] == [x1.id]


def test_only_manual_instruments_can_follow_a_yahoo_one(db: Session, pension):
    fund, x1 = pension
    other_manual = _instrument(db, "MANUAL:OTHER", PriceSource.manual, manual_price_gbp=1.0)
    with pytest.raises(DomainError):
        instrument_service.update_instrument(db, x1, InstrumentUpdate(tracks_instrument_id=fund.id))
    with pytest.raises(DomainError):
        instrument_service.update_instrument(db, fund, InstrumentUpdate(tracks_instrument_id=other_manual.id))
    with pytest.raises(DomainError):
        instrument_service.update_instrument(db, fund, InstrumentUpdate(tracks_instrument_id=fund.id))

    instrument_service.update_instrument(db, fund, InstrumentUpdate(tracks_instrument_id=x1.id))
    instrument_service.update_instrument(db, fund, InstrumentUpdate(tracks_instrument_id=None))
    assert fund.tracks_instrument_id is None
