"""docs/BUILD_PLAN.md Phase 7 task 4 "JSON export": a full dump of the household's data.

Iterates `Base.metadata.sorted_tables` (every table registered via `app/models/__init__.py`)
rather than hand-listing models, so a future table is exported automatically without editing
this file. Each row becomes a plain dict keyed by column name; dates/datetimes are ISO strings
and enums (stored as their `.value` text by SQLAlchemy already) come back as plain strings.
"""
from __future__ import annotations

import datetime as _dt
import decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base


def _jsonable(value: Any) -> Any:
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def export_all(db: Session) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        rows = db.execute(select(table)).mappings().all()
        out[table.name] = [{k: _jsonable(v) for k, v in row.items()} for row in rows]
    return out
