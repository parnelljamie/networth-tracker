from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ImportKind, ImportStatus
from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.accounts import Account
    from app.models.instruments import Instrument


def _enum_column(enum_cls, **kwargs):
    return SAEnum(enum_cls, values_callable=lambda e: [m.value for m in e], **kwargs)


class ImportBatch(TimestampMixin, Base):
    """docs/02-data-model.md "Phase 8: imports" + docs/06-imports-future.md pipeline.

    `mapping_json`, `row_errors_json` and `deleted_stand_ins_json` are stored as TEXT (JSON) —
    SQLite has no native JSON type, so services/importers/service.py (de)serialises with
    `json.dumps`/`json.loads`, matching how other JSON-ish columns are handled elsewhere (see
    settings.value_json in app/models/settings.py).
    """

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[ImportKind] = mapped_column(_enum_column(ImportKind), nullable=False)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    profile_name: Mapped[str | None] = mapped_column(String, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    header_signature: Mapped[str | None] = mapped_column(String, nullable=True)
    mapping_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_imported: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[ImportStatus] = mapped_column(
        _enum_column(ImportStatus), default=ImportStatus.pending, server_default=ImportStatus.pending.value
    )
    row_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    earliest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    deleted_stand_ins_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped[Account] = relationship()


class ImportProfile(Base):
    __tablename__ = "import_profiles"
    __table_args__ = (UniqueConstraint("name", name="uq_import_profiles_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[ImportKind] = mapped_column(_enum_column(ImportKind), nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    header_signature: Mapped[str] = mapped_column(String, nullable=False)


class InstrumentAlias(Base):
    __tablename__ = "instrument_aliases"
    __table_args__ = (
        UniqueConstraint("alias", "profile_name", name="uq_instrument_aliases_alias_profile"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    profile_name: Mapped[str | None] = mapped_column(String, nullable=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )

    instrument: Mapped[Instrument] = relationship()
