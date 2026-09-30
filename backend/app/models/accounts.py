from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Category, ValuationMethod, Wrapper
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.balances import BalanceEntry
    from app.models.db_pension import DbPensionDetails
    from app.models.growth import GrowthModel
    from app.models.loans import LoanDetails
    from app.models.people import Person
    from app.models.positions import Position
    from app.models.property import PropertyDetails
    from app.models.recurring import RecurringPlan
    from app.models.scenarios import ScenarioEvent
    from app.models.snapshots import AccountSnapshot
    from app.models.transactions import Transaction


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[Category] = mapped_column(_enum_column(Category), nullable=False)
    wrapper: Mapped[Wrapper] = mapped_column(
        _enum_column(Wrapper), default=Wrapper.none, server_default=Wrapper.none.value
    )
    valuation_method: Mapped[ValuationMethod] = mapped_column(
        _enum_column(ValuationMethod), nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    include_in_networth: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    is_liquid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_return_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    annual_fee_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    interest_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_balance_gbp: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    opened_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    owners: Mapped[list[AccountOwner]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    balance_entries: Mapped[list[BalanceEntry]] = relationship(
        back_populates="account", cascade="all, delete-orphan", order_by="BalanceEntry.date"
    )
    growth_model: Mapped[GrowthModel | None] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    property_details: Mapped[PropertyDetails | None] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    loan_details: Mapped[LoanDetails | None] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=False,
        primaryjoin="Account.id == LoanDetails.account_id",
        foreign_keys="LoanDetails.account_id",
    )
    db_pension_details: Mapped[DbPensionDetails | None] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=False,
        primaryjoin="Account.id == DbPensionDetails.account_id",
        foreign_keys="DbPensionDetails.account_id",
    )
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="account", cascade="all, delete-orphan", order_by="Transaction.date"
    )
    # Derived/history rows that hang off an account. They have `ondelete="CASCADE"` FKs, but the
    # ORM needs to know about them too so `db.delete(account)` removes them itself rather than
    # relying solely on SQLite enforcing the FK. Deleting an account is now the only removal
    # action in the UI, so these must never be left orphaned.
    snapshots: Mapped[list[AccountSnapshot]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    positions: Mapped[list[Position]] = relationship(cascade="all, delete-orphan")
    recurring_plans: Mapped[list[RecurringPlan]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    # Projection events pointing at this account are meaningless without it -> delete them.
    scenario_events: Mapped[list[ScenarioEvent]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    # Mortgages secured on this account (i.e. this is the property). Deliberately NO delete
    # cascade: the default cascade nulls `secured_on_account_id` when this account goes, matching
    # the FK's `ondelete="SET NULL"`, so the loan account itself survives unlinked.
    loans_secured_on_this: Mapped[list[LoanDetails]] = relationship(
        back_populates="secured_on_account",
        primaryjoin="Account.id == LoanDetails.secured_on_account_id",
        foreign_keys="LoanDetails.secured_on_account_id",
    )


class AccountOwner(Base):
    __tablename__ = "account_owners"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), primary_key=True)
    share: Mapped[float] = mapped_column(Float, nullable=False)

    account: Mapped[Account] = relationship(back_populates="owners")
    person: Mapped[Person] = relationship()
