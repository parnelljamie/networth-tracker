from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin


class BrokerLink(TimestampMixin, Base):
    """A holdings account whose transactions are pulled from a broker's API (Trading 212).

    The API key itself is never stored here: this table travels to the phone and into backups,
    so the key lives in a separate, OS-encrypted file on the PC (services/broker_secrets.py).
    """

    __tablename__ = "broker_links"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False, default="trading212")
    environment: Mapped[str] = mapped_column(String, nullable=False, default="live")
    key_hint: Mapped[str] = mapped_column(String, nullable=False, default="")
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # idle | running | synced | up_to_date | needs_review | error
    status: Mapped[str] = mapped_column(String, nullable=False, default="idle", server_default="idle")
    status_message: Mapped[str | None] = mapped_column(String, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_new_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pending_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
