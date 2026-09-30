# `date` imported as `_Date`: see the note in schemas/balance.py — a field literally named `date`
# with a default shadows a same-named type import during Pydantic's lazy annotation evaluation.
from __future__ import annotations

from datetime import date as _Date

from pydantic import BaseModel, ConfigDict

from app.core.enums import ContributionSource, TxnSource, TxnStatus, TxnType


class TransactionCreate(BaseModel):
    date: _Date
    type: TxnType
    instrument_id: int | None = None
    units: float = 0.0
    price_native: float | None = None
    currency: str = "GBP"
    fx_gbp_per_unit: float = 1.0
    amount_gbp: float
    fees_gbp: float = 0.0
    cost_basis_gbp: float = 0.0
    split_ratio: float | None = None
    contribution_source: ContributionSource | None = None
    notes: str | None = None


class TransactionUpdate(BaseModel):
    date: _Date | None = None
    type: TxnType | None = None
    instrument_id: int | None = None
    units: float | None = None
    price_native: float | None = None
    currency: str | None = None
    fx_gbp_per_unit: float | None = None
    amount_gbp: float | None = None
    fees_gbp: float | None = None
    cost_basis_gbp: float | None = None
    split_ratio: float | None = None
    contribution_source: ContributionSource | None = None
    notes: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    instrument_id: int | None
    date: _Date
    type: TxnType
    units: float
    price_native: float | None
    currency: str
    fx_gbp_per_unit: float
    amount_gbp: float
    fees_gbp: float
    cost_basis_gbp: float
    split_ratio: float | None
    contribution_source: ContributionSource | None
    status: TxnStatus
    source: TxnSource = TxnSource.manual
    import_batch_id: int | None = None
    external_id: str | None = None
    recurring_plan_id: int | None = None
    notes: str | None


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int


class ConfirmItem(BaseModel):
    id: int
    units: float | None = None
    amount_gbp: float | None = None
    price_native: float | None = None


class ConfirmRequest(BaseModel):
    items: list[ConfirmItem]
