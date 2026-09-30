from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import PriceSource
from app.db import Base


class InstrumentPrice(Base):
    __tablename__ = "instrument_prices"

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close_native: Mapped[float] = mapped_column(Float, nullable=False)
    close_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[PriceSource] = mapped_column(
        SAEnum(PriceSource, values_callable=lambda e: [m.value for m in e]), nullable=False
    )


class FxRate(Base):
    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    gbp_per_unit: Mapped[float] = mapped_column(Float, nullable=False)
