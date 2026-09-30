from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.services import backup_service, settings_service


def test_backup_is_also_copied_to_the_chosen_folder(db: Session, tmp_path: Path):
    target = tmp_path / "OneDrive" / "Waymark backups"
    settings_service.update(db, {"backup_copy_dir": str(target)})

    result = backup_service.run_backup_with_copy(db)

    assert result.path.exists()
    assert result.copied_to == target / result.path.name
    assert result.copied_to.exists()
    assert result.copy_error is None


def test_a_failed_copy_keeps_the_local_backup_and_reports_it(db: Session, tmp_path: Path):
    settings_service.update(db, {"backup_copy_dir": str(tmp_path / "gone")})
    # The folder is replaced by a file after being set, e.g. a drive that is no longer there.
    (tmp_path / "gone").rmdir()
    (tmp_path / "gone").write_text("not a folder")

    result = backup_service.run_backup_with_copy(db)

    assert result.path.exists()
    assert result.copied_to is None
    assert result.copy_error


def test_copy_folder_must_be_a_full_path(db: Session):
    with pytest.raises(DomainError):
        settings_service.update(db, {"backup_copy_dir": "OneDrive/backups"})


def test_blank_copy_folder_turns_it_off(db: Session):
    settings_service.update(db, {"backup_copy_dir": "  "})
    assert settings_service.get(db, "backup_copy_dir") == ""
    assert backup_service.run_backup_with_copy(db).copied_to is None
