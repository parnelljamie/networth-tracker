from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.networth import BackupInfoOut, BackupOut
from app.schemas.settings import (
    ChooseFolderIn,
    ChooseFolderOut,
    SystemInfoOut,
    TaxYearRuleIn,
    TaxYearRuleOut,
    UpdateCheckOut,
    UpdateStatusOut,
)
from app.services import (
    backup_service,
    export_service,
    settings_service,
    system_service,
    update_service,
)

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/system/info", response_model=SystemInfoOut)
def system_info() -> SystemInfoOut:
    return system_service.get_info()


@router.post("/system/open-data-folder", response_model=dict[str, str])
def open_data_folder() -> dict[str, str]:
    system_service.open_data_folder()
    return {"status": "ok"}


@router.post("/system/choose-folder", response_model=ChooseFolderOut)
def choose_folder(payload: ChooseFolderIn) -> ChooseFolderOut:
    return ChooseFolderOut(path=system_service.choose_folder(payload.start, payload.title))


# POST, not GET: it goes to the network, and only when the user asks (like prices/refresh).
@router.post("/system/update/check", response_model=UpdateCheckOut)
def check_for_update() -> UpdateCheckOut:
    return update_service.check()


@router.post("/system/update/install", response_model=UpdateStatusOut)
def install_update() -> UpdateStatusOut:
    return update_service.start_install()


@router.get("/system/update/status", response_model=UpdateStatusOut)
def update_status() -> UpdateStatusOut:
    return update_service.get_status()


@router.get("/settings", response_model=dict[str, Any])
def get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_service.get_all(db)


@router.patch("/settings", response_model=dict[str, Any])
def patch_settings(patch: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    return settings_service.update(db, patch)


@router.get("/tax-year-rules", response_model=list[TaxYearRuleOut])
def list_tax_year_rules(db: Session = Depends(get_db)) -> list[TaxYearRuleOut]:
    return settings_service.list_tax_year_rules(db)


@router.put("/tax-year-rules", response_model=TaxYearRuleOut)
def put_tax_year_rule(payload: TaxYearRuleIn, db: Session = Depends(get_db)) -> TaxYearRuleOut:
    return settings_service.upsert_tax_year_rule(db, payload)


@router.post("/backup", response_model=BackupOut)
def backup_now(db: Session = Depends(get_db)) -> BackupOut:
    result = backup_service.run_backup_with_copy(db)
    return BackupOut(
        path=str(result.path),
        copied_to=str(result.copied_to) if result.copied_to else None,
        copy_error=result.copy_error,
    )


@router.get("/backups", response_model=list[BackupInfoOut])
def list_backups() -> list[BackupInfoOut]:
    return [
        BackupInfoOut(filename=b.filename, size_bytes=b.size_bytes, created_at=b.created_at)
        for b in backup_service.list_backups()
    ]


@router.get("/export")
def export_data(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=export_service.export_all(db))
