"""docs/07-mobile.md "Data model additions": PC <-> phone sync."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SyncDevice(Base):
    """A phone paired with this PC. Only the SHA-256 of its token is kept."""

    __tablename__ = "sync_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    paired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SyncAppliedOp(Base):
    """Every op a phone has pushed, so a retried push is applied only once."""

    __tablename__ = "sync_applied_ops"

    op_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("sync_devices.id", ondelete="CASCADE"), nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # applied | rejected
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_map: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON {phone_id: pc_id}


class SyncOutbox(Base):
    """Phone only: an API change made on the phone, waiting to be sent to the PC."""

    __tablename__ = "sync_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    op_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str] = mapped_column(String, nullable=False, default="")
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(String, nullable=False)
