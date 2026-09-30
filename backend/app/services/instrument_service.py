from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import AssetClass, PriceSource
from app.core.errors import DomainError, NotFoundError
from app.models.instruments import Instrument
from app.models.prices import InstrumentPrice
from app.providers.base import PriceProvider
from app.schemas.instrument import InstrumentCreate, InstrumentUpdate
from app.services import price_service


def get_instrument(db: Session, instrument_id: int) -> Instrument:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise NotFoundError(f"Instrument {instrument_id} not found")
    return instrument


def list_instruments(db: Session) -> list[Instrument]:
    return list(db.scalars(select(Instrument).order_by(Instrument.symbol)).all())


def get_by_symbol(db: Session, symbol: str) -> Instrument | None:
    return db.scalars(select(Instrument).where(Instrument.symbol == symbol)).first()


def create_instrument(db: Session, provider: PriceProvider, payload: InstrumentCreate) -> Instrument:
    existing = get_by_symbol(db, payload.symbol)
    if existing is not None:
        # docs/04-api.md: "Existing symbol returns the existing row (200)".
        return existing

    if payload.price_source == PriceSource.manual:
        if payload.manual_price_gbp is None:
            raise DomainError(
                "validation", "A manual instrument needs a starting price", field="manual_price_gbp"
            )
        instrument = Instrument(
            symbol=payload.symbol,
            name=payload.name or payload.symbol,
            quote_currency="GBP",
            asset_class=payload.asset_class or AssetClass.other,
            price_source=PriceSource.manual,
            manual_price_gbp=payload.manual_price_gbp,
            manual_price_date=today(),
        )
        db.add(instrument)
        db.commit()
        db.refresh(instrument)
        return instrument

    try:
        meta = price_service.fetch_metadata(provider, payload.symbol)
    except Exception as e:
        raise DomainError(
            "validation", f"Could not find symbol {payload.symbol!r} on Yahoo", field="symbol"
        ) from e

    instrument = Instrument(
        symbol=payload.symbol,
        name=payload.name or meta.name,
        exchange=meta.exchange,
        quote_type=meta.quote_type,
        quote_currency=meta.currency,
        asset_class=payload.asset_class or AssetClass.equity,
        price_source=PriceSource.yahoo,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)

    price_service.start_background_history_fetch(instrument.id, provider)
    return instrument


def update_instrument(db: Session, instrument: Instrument, payload: InstrumentUpdate) -> Instrument:
    changes = payload.model_dump(exclude_unset=True)
    if "tracks_instrument_id" in changes:
        _check_tracking(db, instrument, changes["tracks_instrument_id"])
    reprice = any(
        field in changes and changes[field] != getattr(instrument, field)
        for field in ("tracks_instrument_id", "manual_price_gbp", "manual_price_date")
    )
    for field, value in changes.items():
        setattr(instrument, field, value)
    db.commit()
    db.refresh(instrument)
    if reprice:
        _rebuild_holders(db, instrument.id)
    return instrument


def _check_tracking(db: Session, instrument: Instrument, target_id: int | None) -> None:
    if target_id is None:
        return
    if instrument.price_source != PriceSource.manual:
        raise DomainError(
            "validation", "Only a manually priced instrument can follow another's price", field="tracks_instrument_id"
        )
    target = db.get(Instrument, target_id)
    if target is None or target.id == instrument.id or target.price_source != PriceSource.yahoo:
        raise DomainError(
            "validation", "Choose an instrument with live prices to follow", field="tracks_instrument_id"
        )


def _rebuild_holders(db: Session, instrument_id: int) -> None:
    """Its price history changed: rebuild every account's snapshots from its first transaction."""
    from app.models.transactions import Transaction
    from app.services import snapshot_service

    firsts = db.execute(
        select(Transaction.account_id, func.min(Transaction.date))
        .where(Transaction.instrument_id == instrument_id)
        .group_by(Transaction.account_id)
    ).all()
    for account_id, first in firsts:
        snapshot_service.request_rebuild(account_id, first)


def list_prices(
    db: Session, instrument_id: int, date_from: date | None, date_to: date | None
) -> list[InstrumentPrice]:
    query = select(InstrumentPrice).where(InstrumentPrice.instrument_id == instrument_id)
    if date_from is not None:
        query = query.where(InstrumentPrice.date >= date_from)
    if date_to is not None:
        query = query.where(InstrumentPrice.date <= date_to)
    return list(db.scalars(query.order_by(InstrumentPrice.date)).all())
