from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ContributionSource, Frequency, PlanKind
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account
    from app.models.instruments import Instrument
    from app.models.scenarios import ScenarioEvent
    from app.models.transactions import Transaction


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class RecurringPlan(TimestampMixin, Base):
    __tablename__ = "recurring_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[PlanKind] = mapped_column(_enum_column(PlanKind), nullable=False)
    amount_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    frequency: Mapped[Frequency] = mapped_column(_enum_column(Frequency), nullable=False)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    annual_increase_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    contribution_source: Mapped[ContributionSource] = mapped_column(
        _enum_column(ContributionSource),
        default=ContributionSource.personal,
        server_default=ContributionSource.personal.value,
    )
    tax_relief_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    auto_record: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    last_recorded_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    account: Mapped[Account] = relationship(back_populates="recurring_plans")
    allocations: Mapped[list[RecurringPlanAllocation]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    # A projection event driven by this plan is meaningless once the plan is gone.
    scenario_events: Mapped[list[ScenarioEvent]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    # Recorded transactions survive the plan; the default cascade nulls their `recurring_plan_id`,
    # matching the FK's `ondelete="SET NULL"`.
    transactions: Mapped[list[Transaction]] = relationship(back_populates="recurring_plan")


class RecurringPlanAllocation(Base):
    __tablename__ = "recurring_plan_allocations"

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("recurring_plans.id", ondelete="CASCADE"), primary_key=True
    )
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    plan: Mapped[RecurringPlan] = relationship(back_populates="allocations")
    instrument: Mapped[Instrument] = relationship()
