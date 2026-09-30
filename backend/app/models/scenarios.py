from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ScenarioEventKind
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account
    from app.models.recurring import RecurringPlan


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class Scenario(TimestampMixin, Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    return_adjustment: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    inflation_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    property_growth_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    events: Mapped[list[ScenarioEvent]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", order_by="ScenarioEvent.date"
    )


class ScenarioEvent(TimestampMixin, Base):
    __tablename__ = "scenario_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[ScenarioEventKind] = mapped_column(_enum_column(ScenarioEventKind), nullable=False)
    # CASCADE on both: a projection event that targets a deleted account, or a deleted recurring
    # plan, is meaningless, so the event row goes with its subject. The ORM equivalents are
    # `Account.scenario_events` / `RecurringPlan.scenario_events`.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("recurring_plans.id", ondelete="CASCADE"), nullable=True
    )
    amount_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String, nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="events")
    account: Mapped[Account | None] = relationship(back_populates="scenario_events")
    plan: Mapped[RecurringPlan | None] = relationship(back_populates="scenario_events")
