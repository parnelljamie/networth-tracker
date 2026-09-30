from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import scenario_service, settings_service


def ensure_defaults(db: Session) -> None:
    settings_service.ensure_defaults(db)
    scenario_service.ensure_defaults(db)
