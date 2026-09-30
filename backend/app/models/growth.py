from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import GrowthMethod
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account


class GrowthModel(TimestampMixin, Base):
    __tablename__ = "growth_models"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    annual_rate: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[GrowthMethod] = mapped_column(
        SAEnum(GrowthMethod, values_callable=lambda e: [m.value for m in e]),
        default=GrowthMethod.compound,
        server_default=GrowthMethod.compound.value,
    )
    floor_value_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    cap_value_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)

    account: Mapped[Account] = relationship(back_populates="growth_model")
