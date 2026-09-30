from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BalanceSource
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account


class BalanceEntry(TimestampMixin, Base):
    __tablename__ = "balance_entries"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uq_balance_entries_account_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    balance_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[BalanceSource] = mapped_column(
        SAEnum(BalanceSource, values_callable=lambda e: [m.value for m in e]),
        default=BalanceSource.manual,
        server_default=BalanceSource.manual.value,
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    account: Mapped[Account] = relationship(back_populates="balance_entries")
