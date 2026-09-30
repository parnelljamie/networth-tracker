from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.enums import PriceSource
from app.models.instruments import Instrument
from app.models.prices import InstrumentPrice
from app.services import price_service
from tests.fakes import FakeProvider


def _instrument(db: Session, symbol: str, currency: str) -> Instrument:
    instrument = Instrument(
        symbol=symbol, name=symbol, quote_currency=currency, price_source=PriceSource.yahoo
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    return instrument


def _hold(db: Session, instrument_id: int) -> None:
    """A Position row is what makes refresh_quotes consider an instrument "held"."""
    from app.core.enums import Category, ValuationMethod, Wrapper
    from app.models.people import Person
    from app.schemas.account import AccountCreate, OwnerShareIn
    from app.schemas.transaction import TransactionCreate
    from app.services import account_service, ledger_service

    person = db.query(Person).first()
    if person is None:
        person = Person(name="James")
        db.add(person)
        db.commit()
        db.refresh(person)

    account = account_service.create_account(
        db,
        AccountCreate(
            name=f"Acc for {instrument_id}",
            category=Category.investment,
            wrapper=Wrapper.gia,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=person.id, share=1.0)],
        ),
    )
    ledger_service.create_transaction(
        db,
        account.id,
        TransactionCreate(date=date(2026, 1, 1), type="BUY", instrument_id=instrument_id, units=1, amount_gbp=-1),
    )


def test_gbp_pence_instrument_valued_in_pounds(db: Session):
    instrument = _instrument(db, "VUSA.L", "GBp")
    _hold(db, instrument.id)
    provider = FakeProvider()
    provider.set_quote("VUSA.L", last=9731.0, prev_close=9700.0, bar_date=date(2026, 9, 15))

    result = price_service.refresh_quotes(db, provider, force=True)

    assert result.status == "ok"
    db.refresh(instrument)
    assert instrument.last_price_gbp == 97.31


def test_usd_instrument_converts_with_fx(db: Session):
    instrument = _instrument(db, "AAPL", "USD")
    _hold(db, instrument.id)
    provider = FakeProvider()
    provider.set_quote("AAPL", last=200.0, prev_close=198.0, bar_date=date(2026, 9, 15))
    provider.set_quote("USDGBP=X", last=0.79, prev_close=0.79, bar_date=date(2026, 9, 15))

    result = price_service.refresh_quotes(db, provider, force=True)

    assert result.status == "ok"
    db.refresh(instrument)
    assert instrument.last_price_gbp == 158.0


def test_100x_glitch_is_corrected(db: Session):
    instrument = _instrument(db, "GLITCH.L", "GBP")
    instrument.last_price_gbp = 100.0
    db.commit()
    _hold(db, instrument.id)
    provider = FakeProvider()
    # A price 100x too high compared to the trusted reference.
    provider.set_quote("GLITCH.L", last=10203.0, prev_close=10100.0, bar_date=date(2026, 9, 15))

    price_service.refresh_quotes(db, provider, force=True)

    db.refresh(instrument)
    assert instrument.last_price_gbp == 102.03


def test_refresh_lock_returns_already_running(db: Session):
    provider = FakeProvider()
    acquired = price_service._refresh_lock.acquire(blocking=False)
    assert acquired
    try:
        result = price_service.refresh_quotes(db, provider, force=True)
        assert result.status == "already_running"
    finally:
        price_service._refresh_lock.release()


def test_price_gbp_manual_instrument(db: Session):
    instrument = Instrument(
        symbol="MANUAL:X",
        name="X",
        quote_currency="GBP",
        price_source=PriceSource.manual,
        manual_price_gbp=42.5,
    )
    result = price_service.price_gbp(db, instrument, date(2026, 9, 15), live=True)
    assert result.price_gbp == 42.5
    assert result.is_stale is False


def _manual_with_history(db: Session) -> Instrument:
    """A manual instrument whose unit-price history was imported (docs/03-domain-logic.md §1)."""
    instrument = Instrument(
        symbol="MANUAL:PEN-FUND",
        name="Pension fund",
        quote_currency="GBP",
        price_source=PriceSource.manual,
        manual_price_gbp=9.696,
        manual_price_date=date(2026, 9, 20),
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    for on, close in ((date(2019, 1, 31), 4.012), (date(2023, 6, 30), 6.55)):
        db.add(
            InstrumentPrice(
                instrument_id=instrument.id, date=on, close_native=close, close_gbp=close,
                source=PriceSource.manual,
            )
        )
    db.commit()
    return instrument


def test_manual_price_uses_imported_history_for_past_dates(db: Session):
    instrument = _manual_with_history(db)

    # On and after a dated row, up to the next one: that row's close, not the typed price.
    assert price_service.price_gbp(db, instrument, date(2019, 1, 31), live=True).price_gbp == 4.012
    assert price_service.price_gbp(db, instrument, date(2021, 5, 4), live=True).price_gbp == 4.012
    assert price_service.price_gbp(db, instrument, date(2023, 6, 30), live=True).price_gbp == 6.55

    # History must not be flagged stale: manual instruments have no provider to go stale.
    assert price_service.price_gbp(db, instrument, date(2021, 5, 4), live=True).is_stale is False


def test_manual_typed_price_wins_once_it_is_the_later_statement(db: Session):
    instrument = _manual_with_history(db)

    # manual_price_date (2026-09-20) postdates every row, so today uses the typed price.
    assert price_service.price_gbp(db, instrument, date(2026, 9, 20), live=True).price_gbp == 9.696

    # Before the typed price was stated, it is not usable at all.
    assert price_service.price_gbp(db, instrument, date(2026, 9, 19), live=True).price_gbp == 6.55


def test_manual_price_falls_back_to_typed_price_before_any_history(db: Session):
    instrument = _manual_with_history(db)

    # Nothing is dated on/before this, so the typed price is a stale fallback rather than zero.
    result = price_service.price_gbp(db, instrument, date(2018, 6, 1), live=True)
    assert result.price_gbp == 9.696
    assert result.is_stale is True
