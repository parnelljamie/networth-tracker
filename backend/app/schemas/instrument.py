from __future__ import annotations

from datetime import date as _Date
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import AssetClass, PriceSource


class InstrumentCreate(BaseModel):
    symbol: str
    price_source: PriceSource = PriceSource.yahoo
    asset_class: AssetClass | None = None
    name: str | None = None
    manual_price_gbp: float | None = None


class InstrumentUpdate(BaseModel):
    name: str | None = None
    asset_class: AssetClass | None = None
    isin: str | None = None
    manual_price_gbp: float | None = None
    manual_price_date: _Date | None = None
    # Manual instruments only: follow this Yahoo instrument between stated prices (null stops).
    tracks_instrument_id: int | None = None


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    isin: str | None
    exchange: str | None
    quote_type: str | None
    quote_currency: str
    asset_class: AssetClass
    price_source: PriceSource
    manual_price_gbp: float | None
    manual_price_date: _Date | None
    tracks_instrument_id: int | None = None
    last_price_native: float | None
    last_price_gbp: float | None
    prev_close_gbp: float | None
    last_price_at: datetime | None
    last_fetch_error: str | None


class InstrumentSearchResultOut(BaseModel):
    symbol: str
    name: str
    exchange: str | None
    quote_type: str | None


class InstrumentPriceOut(BaseModel):
    date: _Date
    close_gbp: float


class RefreshFailure(BaseModel):
    symbol: str
    error: str


class RefreshResultOut(BaseModel):
    status: str
    refreshed: int
    failed: list[RefreshFailure]
    at: datetime


class StaleInstrumentOut(BaseModel):
    instrument_id: int
    symbol: str
    last_price_at: datetime | None


class PricesStatusOut(BaseModel):
    last_refresh_at: datetime | None
    next_refresh_at: datetime | None
    market_open: bool | None
    stale: list[StaleInstrumentOut]
