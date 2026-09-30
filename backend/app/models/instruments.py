from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AssetClass, PriceSource
from app.db import Base
from app.models.mixins import TimestampMixin


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    isin: Mapped[str | None] = mapped_column(String, nullable=True)
    exchange: Mapped[str | None] = mapped_column(String, nullable=True)
    quote_type: Mapped[str | None] = mapped_column(String, nullable=True)
    quote_currency: Mapped[str] = mapped_column(String, nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(
        _enum_column(AssetClass), default=AssetClass.equity, server_default=AssetClass.equity.value
    )
    price_source: Mapped[PriceSource] = mapped_column(_enum_column(PriceSource), nullable=False)
    manual_price_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # A manual instrument can follow a Yahoo-priced one between its own stated prices (e.g. a
    # pension fund's units and the listed share class of the same fund): price_service scales the
    # latest stated price by how far the tracked instrument has moved since that date.
    tracks_instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True
    )
    last_price_native: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_fetch_error: Mapped[str | None] = mapped_column(String, nullable=True)
