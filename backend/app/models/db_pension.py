from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account


class DbPensionDetails(TimestampMixin, Base):
    """Scheme terms for a defined-benefit pension (docs/03-domain-logic.md §1 "defined_benefit").
    Figures come from the member's latest annual benefit statement."""

    __tablename__ = "db_pension_details"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    scheme: Mapped[str] = mapped_column(String, default="tps_2015", server_default="tps_2015")
    accrued_annual_pension_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    accrued_lump_sum_gbp: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    accrued_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    accrual_rate: Mapped[float] = mapped_column(Float, nullable=False)
    revaluation_above_cpi: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    pensionable_salary_gbp: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    salary_growth_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    normal_pension_age: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active_member: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    capitalisation_factor: Mapped[float] = mapped_column(Float, default=20.0, server_default="20")

    account: Mapped[Account] = relationship(back_populates="db_pension_details")
