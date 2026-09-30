from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.people import Person
from app.services import export_service


def test_export_all_on_empty_db_returns_valid_dict_with_expected_tables(db: Session):
    result = export_service.export_all(db)
    assert isinstance(result, dict)
    for table in ("people", "accounts", "transactions", "settings", "tax_year_rules"):
        assert table in result
    # No people/accounts have been created yet.
    assert result["people"] == []
    assert result["accounts"] == []
    # The `db` fixture seeds default settings/tax year rules (seed_service.ensure_defaults), so
    # those tables are non-empty even before any user data exists.
    assert len(result["settings"]) > 0
    assert len(result["tax_year_rules"]) > 0


def test_export_all_includes_people_rows_and_is_json_serialisable(db: Session):
    db.add(Person(name="James"))
    db.commit()

    result = export_service.export_all(db)
    assert len(result["people"]) == 1
    assert result["people"][0]["name"] == "James"

    # Round-trips through json without error (dates/enums already coerced to plain strings).
    json.dumps(result)
