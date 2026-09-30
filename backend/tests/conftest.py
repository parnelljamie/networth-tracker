from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

# Must run before `app` is imported: app.db builds its engine from the data dir at import time.
# Background work (snapshot rebuild threads) opens its own `SessionLocal()` rather than the test
# session, so without this a test run writes to the real data/networth.db, e.g. truncating real
# account history at a frozen test date.
os.environ["NW_DATA_DIR"] = tempfile.mkdtemp(prefix="nw-tests-")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.instruments import get_price_provider
from app.db import Base, get_db
from app.main import app
from app.services import seed_service
from tests.fakes import FakeProvider


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        # Match app/db.py: without this SQLite ignores `ondelete="CASCADE"`, so tests would
        # pass while production cascades (and vice versa).
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = testing_session_local()
    seed_service.ensure_defaults(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture()
def client(db: Session, fake_provider: FakeProvider) -> Iterator[TestClient]:
    def _get_db_override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_price_provider] = lambda: fake_provider
    # No `with`: avoids running the real lifespan (alembic upgrade, scheduler, seeding
    # against the real data dir) — tests own their DB and seeding via the `db` fixture.
    yield TestClient(app)
    app.dependency_overrides.clear()
