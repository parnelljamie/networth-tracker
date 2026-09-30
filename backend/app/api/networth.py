from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.errors import NotFoundError
from app.db import get_db
from app.schemas.allowance import AllowanceUsageOut
from app.schemas.networth import (
    HistorySeriesOut,
    JobStatusOut,
    NetWorthCurrent,
    NetWorthHistory,
    RebuildJobId,
    RebuildRequest,
)
from app.services import allowances_service, networth_service, snapshot_service

router = APIRouter(prefix="/api", tags=["networth"])


@router.get("/networth/current", response_model=NetWorthCurrent)
def get_current(person_id: int | None = None, db: Session = Depends(get_db)) -> NetWorthCurrent:
    return networth_service.get_current(db, person_id=person_id)


@router.get("/networth/history", response_model=NetWorthHistory)
def get_history(
    person_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = "day",
    group_by: str = "category",
    db: Session = Depends(get_db),
) -> NetWorthHistory:
    on = today()
    result = snapshot_service.history(
        db,
        person_id=person_id,
        date_from=date_from or date(on.year - 5, on.month, on.day),
        date_to=date_to or on,
        granularity=granularity,
        group_by=group_by,
    )
    return NetWorthHistory(
        dates=result.dates,
        total=result.total,
        series=[HistorySeriesOut(key=s.key, label=s.label, values=s.values) for s in result.series],
    )


@router.get("/allowances", response_model=list[AllowanceUsageOut])
def get_allowances(
    tax_year: int | None = None, person_id: int | None = None, db: Session = Depends(get_db)
) -> list[AllowanceUsageOut]:
    return allowances_service.usage(db, tax_year=tax_year, person_id=person_id)


@router.post("/snapshots/rebuild", response_model=RebuildJobId)
def rebuild_snapshots(payload: RebuildRequest) -> RebuildJobId:
    job_id = snapshot_service.start_rebuild_job(payload.account_id, payload.from_date)
    return RebuildJobId(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str) -> JobStatusOut:
    job = snapshot_service.get_job(job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found")
    return JobStatusOut(status=job.status, progress=job.progress, error=job.error)
