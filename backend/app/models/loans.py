from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OverpaymentEffect, RateType, RepaymentType
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class LoanDetails(TimestampMixin, Base):
    __tablename__ = "loan_details"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    # SET NULL, not CASCADE: deleting the property a mortgage is secured on must not delete the
    # mortgage. The loan survives and simply becomes unlinked (`loan_service.equity()` matches on
    # `secured_on_account_id == property.id`, so a NULL link just stops appearing under any
    # property). The ORM side is `Account.loans_secured_on_this`, whose default cascade nulls the
    # column out on flush so this is correct even without SQLite enforcing the FK.
    secured_on_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    lender: Mapped[str | None] = mapped_column(String, nullable=True)
    original_amount_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    repayment_type: Mapped[RepaymentType] = mapped_column(
        _enum_column(RepaymentType), default=RepaymentType.repayment,
        server_default=RepaymentType.repayment.value,
    )
    payment_day: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    overpayment_effect: Mapped[OverpaymentEffect] = mapped_column(
        _enum_column(OverpaymentEffect), default=OverpaymentEffect.reduce_term,
        server_default=OverpaymentEffect.reduce_term.value,
    )
    overpayment_allowance_rate: Mapped[float] = mapped_column(
        Float, default=0.10, server_default="0.10"
    )
    fallback_rate: Mapped[float] = mapped_column(Float, nullable=False)

    account: Mapped[Account] = relationship(
        back_populates="loan_details", foreign_keys=[account_id]
    )
    secured_on_account: Mapped[Account | None] = relationship(
        back_populates="loans_secured_on_this", foreign_keys=[secured_on_account_id]
    )
    rate_periods: Mapped[list[LoanRatePeriod]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="LoanRatePeriod.start_date",
        primaryjoin="LoanDetails.account_id == LoanRatePeriod.account_id",
        foreign_keys="LoanRatePeriod.account_id",
    )
    overpayments: Mapped[list[LoanOverpayment]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="LoanOverpayment.date",
        primaryjoin="LoanDetails.account_id == LoanOverpayment.account_id",
        foreign_keys="LoanOverpayment.account_id",
    )


class LoanRatePeriod(TimestampMixin, Base):
    __tablename__ = "loan_rate_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_rate: Mapped[float] = mapped_column(Float, nullable=False)
    rate_type: Mapped[RateType] = mapped_column(_enum_column(RateType), nullable=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_override_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    erc_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    account: Mapped[LoanDetails] = relationship(
        back_populates="rate_periods",
        primaryjoin="LoanRatePeriod.account_id == LoanDetails.account_id",
        foreign_keys=[account_id],
    )


class LoanOverpayment(TimestampMixin, Base):
    __tablename__ = "loan_overpayments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    is_planned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    account: Mapped[LoanDetails] = relationship(
        back_populates="overpayments",
        primaryjoin="LoanOverpayment.account_id == LoanDetails.account_id",
        foreign_keys=[account_id],
    )
