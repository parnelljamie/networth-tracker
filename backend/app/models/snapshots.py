from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SnapshotSource
from app.db import Base

if TYPE_CHECKING:
    from app.models.accounts import Account


class AccountSnapshot(Base):
    """docs/02-data-model.md "account_snapshots": one row per account per calendar day.

    Charts read only from here — no audit columns beyond `created_at`.
    """

    __tablename__ = "account_snapshots"
    __table_args__ = (Index("ix_account_snapshots_date", "date"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_contributions_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    source: Mapped[SnapshotSource] = mapped_column(
        SAEnum(SnapshotSource, values_callable=lambda e: [m.value for m in e]),
        default=SnapshotSource.daily,
        server_default=SnapshotSource.daily.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="snapshots")
