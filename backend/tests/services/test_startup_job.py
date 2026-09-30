"""Issue #21: recurring plans must be recorded at startup, not only by the 07:00 trigger."""

from __future__ import annotations

import pytest

from app import jobs


class _NullSession:
    def __enter__(self) -> _NullSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture()
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    recorded: list[str] = []
    monkeypatch.setattr(jobs, "SessionLocal", _NullSession)
    monkeypatch.setattr(jobs.recurring_service, "record_due", lambda db, on: recorded.append("record_due") or [])
    monkeypatch.setattr(jobs.snapshot_service, "catch_up", lambda db, provider: recorded.append("catch_up"))
    return recorded


def test_startup_records_due_plans_before_catching_up(calls: list[str]):
    jobs.startup_job()
    assert calls == ["record_due", "catch_up"]


def test_startup_still_catches_up_when_record_due_fails(calls: list[str], monkeypatch: pytest.MonkeyPatch):
    def boom(db: object, on: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(jobs.recurring_service, "record_due", boom)
    jobs.startup_job()
    assert calls == ["catch_up"]
