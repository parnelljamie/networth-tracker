from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.settings import Setting
from app.models.tax_year_rules import TaxYearRule
from app.schemas.settings import TaxYearRuleIn

# docs/02-data-model.md "Configuration" — seeded defaults.
DEFAULTS: dict[str, Any] = {
    "inflation_rate": 0.025,
    "default_return_rates": {
        "equity": 0.06,
        "bond": 0.035,
        "multi_asset": 0.05,
        "property": 0.03,
        "commodity": 0.02,
        "cash": 0.035,
        "crypto": 0.0,
        "other": 0.03,
    },
    "default_volatility": {
        "equity": 0.16,
        "bond": 0.06,
        "multi_asset": 0.11,
        "property": 0.12,
        "commodity": 0.18,
        "cash": 0.0,
        "crypto": 0.7,
        "other": 0.1,
    },
    "price_refresh_minutes": 15,
    "projection_horizon_years": 30,
    "projection_real_terms": False,
    "stale_balance_days": {"warn": 35, "alert": 90},
    "pension_access_age": 57,
    "deposit_protection_limit_gbp": 120000,
    "backup_keep": 30,
    # Optional second folder each backup is also copied to (e.g. a OneDrive folder). "" = off.
    "backup_copy_dir": "",
    "privacy_mode_default": False,
    # docs/07-mobile.md: the LAN listener phones sync with. Changed through /api/sync.
    "sync_enabled": False,
    "sync_port": 8766,
}

TAX_YEAR_DEFAULTS: list[dict[str, Any]] = [
    {
        "tax_year_start": year,
        "isa_allowance_gbp": 20000,
        "lisa_allowance_gbp": 4000,
        "jisa_allowance_gbp": 9000,
        "cash_isa_limit_gbp": None,
        "pension_annual_allowance_gbp": 60000,
    }
    for year in (2024, 2025, 2026)
]


def ensure_defaults(db: Session) -> None:
    existing_settings = set(db.scalars(select(Setting.key)).all())
    for key, value in DEFAULTS.items():
        if key not in existing_settings:
            db.add(Setting(key=key, value=value))

    existing_years = set(db.scalars(select(TaxYearRule.tax_year_start)).all())
    for row in TAX_YEAR_DEFAULTS:
        if row["tax_year_start"] not in existing_years:
            db.add(TaxYearRule(**row))

    db.commit()


def get_all(db: Session) -> dict[str, Any]:
    rows = db.scalars(select(Setting)).all()
    values = dict(DEFAULTS)
    values.update({row.key: row.value for row in rows})
    return values


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    if row is not None:
        return row.value
    return DEFAULTS.get(key, default)


def update(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    unknown = set(patch) - set(DEFAULTS)
    if unknown:
        raise DomainError("validation", f"Unknown settings: {sorted(unknown)}", field=None)
    if "backup_copy_dir" in patch:
        from app.services import backup_service

        patch = {**patch, "backup_copy_dir": backup_service.validate_copy_dir(patch["backup_copy_dir"])}
    for key, value in patch.items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()

    from app.services import projection_service

    projection_service.bump_data_version()
    return get_all(db)


def list_tax_year_rules(db: Session) -> list[TaxYearRule]:
    return list(db.scalars(select(TaxYearRule).order_by(TaxYearRule.tax_year_start)).all())


def upsert_tax_year_rule(db: Session, payload: TaxYearRuleIn) -> TaxYearRule:
    row = db.get(TaxYearRule, payload.tax_year_start)
    if row is None:
        row = TaxYearRule(**payload.model_dump())
        db.add(row)
    else:
        for field, value in payload.model_dump(exclude={"tax_year_start"}).items():
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
