from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date as SADate
from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.instruments import Instrument


class Position(Base):
    """Cache rebuilt by ledger_service.rebuild_positions(). Never written to directly."""

    __tablename__ = "positions"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    units: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    realised_gain_gbp: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    first_date: Mapped[date | None] = mapped_column(SADate, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    instrument: Mapped[Instrument] = relationship()
