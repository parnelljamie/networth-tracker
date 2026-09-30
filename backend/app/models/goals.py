"""docs/02-data-model.md "Phase 7: goals"."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Category, GoalScope
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account
    from app.models.people import Person


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class Goal(TimestampMixin, Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    target_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scope: Mapped[GoalScope] = mapped_column(_enum_column(GoalScope), nullable=False)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )
    category: Mapped[Category | None] = mapped_column(_enum_column(Category), nullable=True)

    person: Mapped[Person | None] = relationship()
    account: Mapped[Account | None] = relationship()
