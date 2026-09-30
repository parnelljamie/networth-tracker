from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.attribution import AttributionOut
from app.schemas.insights import DepositProtectionOut
from app.services import attribution_service, insights_service

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/attribution", response_model=AttributionOut)
def get_attribution(
    start: date, end: date, person_id: int | None = None, db: Session = Depends(get_db)
) -> AttributionOut:
    return attribution_service.attribution(db, start, end, person_id=person_id)


@router.get("/deposit-protection", response_model=DepositProtectionOut)
def get_deposit_protection(db: Session = Depends(get_db)) -> DepositProtectionOut:
    return insights_service.deposit_protection(db)
