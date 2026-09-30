from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.instruments import get_price_provider
from app.core.enums import ImportKind
from app.db import get_db
from app.providers.base import PriceProvider
from app.schemas.imports import (
    CommitIn,
    CommitOut,
    ImportBatchOut,
    JobStatusOut,
    PreviewIn,
    PreviewOut,
    ReconciliationRow,
    ResolveInstrumentsIn,
    RowErrorOut,
    SaveMappingIn,
    UnmatchedInstrument,
    UploadResult,
)
from app.services.importers import service as import_service

router = APIRouter(prefix="/api", tags=["imports"])


def _preview_out(batch, result: import_service.PreviewResult) -> PreviewOut:
    return PreviewOut(
        batch=ImportBatchOut.model_validate(batch),
        counts_by_type=result.counts_by_type,
        date_from=result.date_from,
        date_to=result.date_to,
        row_errors=[RowErrorOut(row=e.row, message=e.message) for e in result.row_errors],
        ledger_warnings=result.ledger_warnings,
        reconciliation=[
            ReconciliationRow(
                instrument_id=r.instrument_id,
                symbol=r.symbol,
                name=r.name,
                current_units=r.current_units,
                current_avg_cost_gbp=r.current_avg_cost_gbp,
                imported_units=r.imported_units,
                imported_avg_cost_gbp=r.imported_avg_cost_gbp,
                units_diff=r.units_diff,
                avg_cost_diff_gbp=r.avg_cost_diff_gbp,
            )
            for r in result.reconciliation
        ],
        unmatched_instruments=[
            UnmatchedInstrument(key=u.key, symbol=u.symbol, isin=u.isin, name=u.name, suggestions=u.suggestions)
            for u in result.unmatched_instruments
        ],
        cash_diff_gbp=result.cash_diff_gbp,
        ready=result.ready,
    )


@router.get("/imports", response_model=list[ImportBatchOut])
def list_imports(db: Session = Depends(get_db)) -> list[ImportBatchOut]:
    return import_service.list_batches(db)


@router.get("/imports/{batch_id}", response_model=ImportBatchOut)
def get_import(batch_id: int, db: Session = Depends(get_db)) -> ImportBatchOut:
    return import_service.get_batch(db, batch_id)


@router.post("/imports", response_model=UploadResult, status_code=201)
def create_import(
    kind: ImportKind = Form(...),
    account_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResult:
    content = file.file.read()
    batch, headers, sample_rows, matched_profile = import_service.upload(
        db, kind, account_id, file.filename or "upload.csv", content
    )
    return UploadResult(
        batch=ImportBatchOut.model_validate(batch),
        headers=headers,
        sample_rows=sample_rows,
        matched_profile=matched_profile,
    )


@router.post("/imports/{batch_id}/mapping", response_model=ImportBatchOut)
def save_mapping(batch_id: int, payload: SaveMappingIn, db: Session = Depends(get_db)) -> ImportBatchOut:
    batch = import_service.get_batch(db, batch_id)
    mapping = {k: v.model_dump(exclude_none=True) for k, v in payload.mapping.items()}
    return import_service.save_mapping(db, batch, payload.profile_name, mapping, payload.save_as_profile)


@router.post("/imports/{batch_id}/instruments", status_code=204)
def resolve_instruments(
    batch_id: int, payload: ResolveInstrumentsIn, db: Session = Depends(get_db)
) -> None:
    batch = import_service.get_batch(db, batch_id)
    import_service.resolve_instruments(db, batch, [(r.key, r.instrument_id) for r in payload.resolutions])


@router.post("/imports/{batch_id}/preview", response_model=PreviewOut)
def preview_import(
    batch_id: int,
    payload: PreviewIn,
    db: Session = Depends(get_db),
    provider: PriceProvider = Depends(get_price_provider),
) -> PreviewOut:
    batch = import_service.get_batch(db, batch_id)
    result = import_service.preview(db, batch, provider, payload.anchor_balance_gbp, payload.anchor_date)
    return _preview_out(batch, result)


@router.post("/imports/{batch_id}/commit", response_model=CommitOut)
def commit_import(
    batch_id: int,
    payload: CommitIn,
    db: Session = Depends(get_db),
    provider: PriceProvider = Depends(get_price_provider),
) -> CommitOut:
    batch = import_service.get_batch(db, batch_id)
    batch, job_id = import_service.commit(
        db,
        batch,
        provider,
        payload.replace_stand_ins,
        payload.align_to_current,
        payload.anchor_balance_gbp,
        payload.anchor_date,
    )
    return CommitOut(batch=ImportBatchOut.model_validate(batch), job_id=job_id)


@router.post("/imports/{batch_id}/rollback", response_model=ImportBatchOut)
def rollback_import(batch_id: int, db: Session = Depends(get_db)) -> ImportBatchOut:
    batch = import_service.get_batch(db, batch_id)
    return import_service.rollback(db, batch)


@router.get("/imports/jobs/{job_id}", response_model=JobStatusOut)
def get_job_status(job_id: str) -> JobStatusOut:
    job = import_service.get_job(job_id)
    if job is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Job {job_id} not found")
    return JobStatusOut(status=job.status, progress=job.progress, error=job.error)
