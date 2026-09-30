from __future__ import annotations

from datetime import date as _Date
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ImportKind, ImportStatus


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: ImportKind
    account_id: int
    profile_name: str | None
    filename: str
    header_signature: str | None
    imported_at: datetime | None
    rows_total: int
    rows_imported: int
    rows_skipped: int
    status: ImportStatus
    earliest_date: _Date | None
    created_at: datetime


class UploadResult(BaseModel):
    batch: ImportBatchOut
    headers: list[str]
    sample_rows: list[dict]
    matched_profile: str | None = None


class ColumnMappingField(BaseModel):
    column: str | None = None
    format: str | None = None
    values: dict[str, str] | None = None
    sign_from_type: bool | None = None


class SaveMappingIn(BaseModel):
    profile_name: str
    mapping: dict[str, ColumnMappingField]
    save_as_profile: bool = True


class UnmatchedInstrument(BaseModel):
    key: str
    symbol: str | None
    isin: str | None
    name: str | None
    suggestions: list[dict]


class InstrumentResolutionIn(BaseModel):
    key: str
    instrument_id: int


class ResolveInstrumentsIn(BaseModel):
    resolutions: list[InstrumentResolutionIn]


class RowErrorOut(BaseModel):
    row: int
    message: str


class ReconciliationRow(BaseModel):
    instrument_id: int | None
    symbol: str | None
    name: str | None
    current_units: float
    current_avg_cost_gbp: float
    imported_units: float
    imported_avg_cost_gbp: float
    units_diff: float
    avg_cost_diff_gbp: float


class PreviewIn(BaseModel):
    anchor_balance_gbp: float | None = None
    anchor_date: _Date | None = None


class PreviewOut(BaseModel):
    batch: ImportBatchOut
    counts_by_type: dict[str, int]
    date_from: _Date | None
    date_to: _Date | None
    row_errors: list[RowErrorOut]
    ledger_warnings: list[str]
    reconciliation: list[ReconciliationRow]
    unmatched_instruments: list[UnmatchedInstrument]
    cash_diff_gbp: float | None = None
    ready: bool


class CommitIn(BaseModel):
    replace_stand_ins: bool = True
    align_to_current: bool = False
    anchor_balance_gbp: float | None = None
    anchor_date: _Date | None = None


class CommitOut(BaseModel):
    batch: ImportBatchOut
    job_id: str | None = None


class JobStatusOut(BaseModel):
    status: str
    progress: float
    error: str | None = None
