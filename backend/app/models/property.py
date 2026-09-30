from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account


class PropertyDetails(TimestampMixin, Base):
    __tablename__ = "property_details"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_main_residence: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    account: Mapped[Account] = relationship(back_populates="property_details")
