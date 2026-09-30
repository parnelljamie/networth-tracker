from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TaxYearRuleIn(BaseModel):
    tax_year_start: int
    isa_allowance_gbp: float
    lisa_allowance_gbp: float
    jisa_allowance_gbp: float
    cash_isa_limit_gbp: float | None = None
    pension_annual_allowance_gbp: float


class TaxYearRuleOut(TaxYearRuleIn):
    model_config = ConfigDict(from_attributes=True)


class SystemInfoOut(BaseModel):
    version: str
    data_dir: str


class UpdateCheckOut(BaseModel):
    current_version: str
    latest_version: str
    update_available: bool
    platform: Literal["windows", "android", "linux"]
    release_url: str
    notes: str
    # The download for this platform, if the release has one.
    asset_name: str | None = None
    asset_url: str | None = None
    asset_sha256: str | None = None
    asset_size: int | None = None
    # True only in the installed Windows app, which downloads and runs the installer itself.
    can_install: bool = False


class UpdateStatusOut(BaseModel):
    state: Literal["idle", "downloading", "installing", "error"]
    version: str | None = None
    downloaded: int = 0
    total: int | None = None
    error: str | None = None


class ChooseFolderIn(BaseModel):
    start: str | None = None  # folder to open the picker at
    title: str = "Choose a folder"


class ChooseFolderOut(BaseModel):
    path: str | None  # None when the user cancelled
