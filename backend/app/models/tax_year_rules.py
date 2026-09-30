from __future__ import annotations

from sqlalchemy import Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin


class TaxYearRule(TimestampMixin, Base):
    __tablename__ = "tax_year_rules"

    tax_year_start: Mapped[int] = mapped_column(Integer, primary_key=True)
    isa_allowance_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    lisa_allowance_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    jisa_allowance_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    cash_isa_limit_gbp: Mapped[float | None] = mapped_column(Float, nullable=True)
    pension_annual_allowance_gbp: Mapped[float] = mapped_column(Float, nullable=False)
