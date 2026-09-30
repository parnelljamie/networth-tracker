from __future__ import annotations

from datetime import date as _Date
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.imports import ReconciliationRow, UnmatchedInstrument


class Trading212ConnectIn(BaseModel):
    api_key: str
    # Keys created since Trading 212 added secrets come as a key + secret pair; older keys
    # have no secret.
    api_secret: str = ""
    environment: Literal["live", "demo"] = "live"


class Trading212NewAccountIn(Trading212ConnectIn):
    """Settings → Connect Trading 212: create the account and link it in one go. The API can't
    tell a Stocks ISA key from an Invest one, so the user says which."""

    account_type: Literal["isa", "invest"]
    owner_person_id: int
    name: str | None = None


class Trading212LinkUpdate(BaseModel):
    auto_sync: bool


class Trading212LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    environment: str
    key_hint: str
    auto_sync: bool
    # idle | running | synced | up_to_date | needs_review | error
    status: str
    status_message: str | None = None
    last_synced_at: datetime | None = None
    last_new_rows: int
    pending_batch_id: int | None = None


class Trading212ChangeRow(BaseModel):
    date: _Date
    type: str
    symbol: str | None
    name: str | None
    units: float
    amount_gbp: float


class Trading212ChangesOut(BaseModel):
    """A sync waiting for the user to accept it (the app-wide popup)."""

    account_id: int
    account_name: str
    batch_id: int
    first_sync: bool
    message: str | None = None
    transactions: list[Trading212ChangeRow]
    # Every holding the sync touches: units and average cost now and once accepted.
    holdings: list[ReconciliationRow]
    cash_before_gbp: float
    cash_after_gbp: float
    unmatched_instruments: list[UnmatchedInstrument]
    ledger_warnings: list[str]
    ready: bool
