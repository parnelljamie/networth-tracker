from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.providers.base import PriceProvider
from app.providers.factory import default_provider
from app.schemas.instrument import (
    InstrumentCreate,
    InstrumentOut,
    InstrumentPriceOut,
    InstrumentSearchResultOut,
    InstrumentUpdate,
    PricesStatusOut,
    RefreshResultOut,
    StaleInstrumentOut,
)
from app.services import instrument_service, price_service, snapshot_service

router = APIRouter(prefix="/api", tags=["instruments"])

_default_provider = default_provider()


def get_price_provider() -> PriceProvider:
    """Overridden in tests (see tests/conftest.py) so nothing here ever touches the network."""
    return _default_provider


@router.get("/instruments/search", response_model=list[InstrumentSearchResultOut])
def search_instruments(q: str, provider: PriceProvider = Depends(get_price_provider)) -> list[InstrumentSearchResultOut]:
    return price_service.search(provider, q)


@router.post("/instruments", response_model=InstrumentOut, status_code=201)
def create_instrument(
    payload: InstrumentCreate,
    db: Session = Depends(get_db),
    provider: PriceProvider = Depends(get_price_provider),
) -> InstrumentOut:
    return instrument_service.create_instrument(db, provider, payload)


@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(db: Session = Depends(get_db)) -> list[InstrumentOut]:
    return instrument_service.list_instruments(db)


@router.get("/instruments/{instrument_id}", response_model=InstrumentOut)
def get_instrument(instrument_id: int, db: Session = Depends(get_db)) -> InstrumentOut:
    return instrument_service.get_instrument(db, instrument_id)


@router.patch("/instruments/{instrument_id}", response_model=InstrumentOut)
def update_instrument(
    instrument_id: int, payload: InstrumentUpdate, db: Session = Depends(get_db)
) -> InstrumentOut:
    instrument = instrument_service.get_instrument(db, instrument_id)
    return instrument_service.update_instrument(db, instrument, payload)


@router.get("/instruments/{instrument_id}/prices", response_model=list[InstrumentPriceOut])
def instrument_prices(
    instrument_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> list[InstrumentPriceOut]:
    instrument_service.get_instrument(db, instrument_id)
    return instrument_service.list_prices(db, instrument_id, date_from, date_to)


@router.post("/prices/refresh", response_model=RefreshResultOut)
def refresh_prices(
    force: bool = False,
    db: Session = Depends(get_db),
    provider: PriceProvider = Depends(get_price_provider),
) -> RefreshResultOut:
    result = snapshot_service.refresh_quotes(db, provider, force=force)
    return RefreshResultOut(
        status=result.status, refreshed=result.refreshed, failed=result.failed, at=result.at
    )


@router.get("/prices/status", response_model=PricesStatusOut)
def prices_status(db: Session = Depends(get_db)) -> PricesStatusOut:
    instruments = price_service.held_yahoo_instruments(db)
    last_refresh_at = max(
        (i.last_price_at for i in instruments if i.last_price_at is not None), default=None
    )
    stale = [
        StaleInstrumentOut(instrument_id=i.id, symbol=i.symbol, last_price_at=i.last_price_at)
        for i in instruments
        if i.last_fetch_error is not None
    ]
    return PricesStatusOut(last_refresh_at=last_refresh_at, next_refresh_at=None, market_open=None, stale=stale)
