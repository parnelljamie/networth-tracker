from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ContributionSource, TxnSource, TxnStatus, TxnType
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account
    from app.models.instruments import Instrument
    from app.models.recurring import RecurringPlan


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_date", "account_id", "date"),
        # Not a unique constraint: dedupe against (account_id, external_id) is enforced in
        # services/importers (a row may legitimately have external_id = NULL), this index just
        # makes that lookup fast.
        Index("ix_transactions_account_external_id", "account_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[TxnType] = mapped_column(_enum_column(TxnType), nullable=False)
    units: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    price_native: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="GBP", server_default="GBP")
    fx_gbp_per_unit: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    amount_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    fees_gbp: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    cost_basis_gbp: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    split_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    contribution_source: Mapped[ContributionSource | None] = mapped_column(
        _enum_column(ContributionSource), nullable=True
    )
    status: Mapped[TxnStatus] = mapped_column(
        _enum_column(TxnStatus), default=TxnStatus.confirmed, server_default=TxnStatus.confirmed.value
    )
    source: Mapped[TxnSource] = mapped_column(
        _enum_column(TxnSource), default=TxnSource.manual, server_default=TxnSource.manual.value
    )
    # SET NULL: a transaction is real recorded history and must outlive the plan that generated
    # it (plans are deletable on their own, and deleting an account now cascades to its plans).
    recurring_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_plans.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)

    account: Mapped[Account] = relationship(back_populates="transactions")
    instrument: Mapped[Instrument | None] = relationship()
    recurring_plan: Mapped[RecurringPlan | None] = relationship(back_populates="transactions")
