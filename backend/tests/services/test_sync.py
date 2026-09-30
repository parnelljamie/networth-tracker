"""docs/07-mobile.md "Tests": PC <-> phone sync."""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.instruments import get_price_provider
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models.accounts import Account
from app.models.balances import BalanceEntry
from app.models.people import Person
from app.models.sync import SyncAppliedOp, SyncOutbox
from app.models.transactions import Transaction
from app.services import seed_service
from app.services.sync import apply, client, devices, ids, lan, outbox, snapshot
from app.services.sync.ids import PHONE_ID_BASE
from tests.fakes import FakeProvider


@pytest.fixture()
def phone_role(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "role", "phone")
    ids.reset_counter()
    yield
    ids.reset_counter()


def _person(c: TestClient, name: str = "Alex") -> dict:
    return c.post("/api/people", json={"name": name}).json()


def _cash_account(c: TestClient, person_id: int, name: str = "Current") -> dict:
    return c.post(
        "/api/accounts",
        json={
            "name": name,
            "category": "cash",
            "valuation_method": "balance",
            "owners": [{"person_id": person_id, "share": 1.0}],
        },
    ).json()


# --- ids ---------------------------------------------------------------------------------------


def test_phone_role_allocates_ids_from_the_phone_range(client: TestClient, phone_role: None):
    first = _person(client)
    second = _person(client, "Sam")
    assert first["id"] == PHONE_ID_BASE
    assert second["id"] == PHONE_ID_BASE + 1


def test_phone_ids_are_unique_across_tables(client: TestClient, phone_role: None):
    """A balance entry and an account must never share a phone id, or the PC could map one to
    the other."""
    person = _person(client)
    existing = _cash_account(client, person["id"])
    entry = client.post(
        f"/api/accounts/{existing['id']}/balances", json={"date": "2026-09-01", "balance_gbp": 1}
    ).json()
    account = _cash_account(client, person["id"], "Second")
    assert len({person["id"], existing["id"], entry["id"], account["id"]}) == 4


def test_the_counter_resumes_above_every_table_after_a_restart(client: TestClient, phone_role: None):
    person = _person(client)
    entry_owner = _cash_account(client, person["id"])
    entry = client.post(
        f"/api/accounts/{entry_owner['id']}/balances", json={"date": "2026-09-01", "balance_gbp": 1}
    ).json()
    ids.reset_counter()  # as after the app restarts
    goal = client.post("/api/goals", json={"name": "Big", "target_gbp": 1, "scope": "household"}).json()
    assert goal["id"] > entry["id"]


def test_desktop_role_ids_are_unchanged(client: TestClient):
    assert _person(client)["id"] < 1000


# --- outbox ------------------------------------------------------------------------------------


def test_outbox_records_successful_changes_only(client: TestClient, db: Session, phone_role: None):
    person = _person(client)
    account = _cash_account(client, person["id"])
    r = client.post(f"/api/accounts/{account['id']}/balances", json={"date": "2026-09-01", "balance_gbp": 1200})
    assert r.status_code == 201

    client.post("/api/prices/refresh")  # local only
    bad = client.post(f"/api/accounts/{account['id']}/balances", json={"date": "nope", "balance_gbp": 1})
    assert bad.status_code == 422

    ops = outbox.list_ops(db)
    assert [o.summary for o in ops] == [
        "New person: Alex",
        "New account: Current",
        "Balance £1,200.00 for Current on 1 Sep 2026",
    ]
    assert ops[2].path == f"/api/accounts/{account['id']}/balances"
    assert json.loads(ops[2].body)["balance_gbp"] == 1200
    assert json.loads(ops[1].response)["id"] == account["id"]


def test_summaries_read_as_plain_english(client: TestClient, db: Session):
    from app.services.sync.describe import describe

    person = _person(client)
    account = client.post(
        "/api/accounts",
        json={
            "name": "ISA",
            "category": "investment",
            "wrapper": "isa",
            "valuation_method": "holdings",
            "owners": [{"person_id": person["id"], "share": 1.0}],
        },
    ).json()
    instrument = client.post(
        "/api/instruments", json={"symbol": "VWRL.L", "price_source": "manual", "manual_price_gbp": 100}
    ).json()
    a, i = account["id"], instrument["id"]

    buy = {"date": "2026-09-02", "type": "BUY", "instrument_id": i, "units": 2.5, "amount_gbp": -250}
    assert describe(db, "POST", f"/api/accounts/{a}/transactions", buy) == "Buy 2.5 VWRL.L in ISA on 2 Sep 2026"
    fee = {"date": "2026-09-03", "type": "FEE", "amount_gbp": -4.5}
    assert describe(db, "POST", f"/api/accounts/{a}/transactions", fee) == "Fee −£4.50 in ISA on 3 Sep 2026"
    assert describe(db, "PUT", f"/api/accounts/{a}/holdings/{i}", {"units": 10}) == "Set VWRL.L in ISA to 10 units"
    assert describe(db, "DELETE", f"/api/accounts/{a}", None) == "Deleted ISA"
    bulk = {"entries": [{}, {}, {}]}
    assert describe(db, "POST", "/api/balances/bulk", bulk) == "Quick update of 3 balances"
    assert describe(db, "PATCH", "/api/goals/4", {"name": "x"}) == "Changed a goal"
    assert describe(db, "PATCH", "/api/settings", {}) == "Changed settings"


def test_desktop_role_records_nothing(client: TestClient, db: Session):
    _person(client)
    assert outbox.pending_count(db) == 0


def test_changes_are_refused_while_syncing(client: TestClient, db: Session, phone_role: None):
    lock = outbox.sync_lock()
    lock.acquire()
    try:
        r = client.post("/api/people", json={"name": "Alex"})
        assert r.status_code == 423
        assert r.json()["error"]["code"] == "sync_in_progress"
        assert client.get("/api/people").status_code == 200  # reads still work
    finally:
        lock.release()
    assert outbox.pending_count(db) == 0


# --- applying a push on the PC -----------------------------------------------------------------


def _phone_ops_new_account_with_balance() -> list[apply.Op]:
    """What the phone's outbox holds after: add a person, an account for them, a balance on it."""
    p, a = PHONE_ID_BASE, PHONE_ID_BASE + 1
    return [
        apply.Op("op-1", "POST", "/api/people", body={"name": "Alex"}, response={"id": p, "name": "Alex"}),
        apply.Op(
            "op-2",
            "POST",
            "/api/accounts",
            body={
                "name": "Phone saver",
                "category": "cash",
                "valuation_method": "balance",
                "owners": [{"person_id": p, "share": 1.0}],
            },
            response={"id": a, "owners": [{"person_id": p, "share": 1.0}]},
        ),
        apply.Op(
            "op-3",
            "POST",
            f"/api/accounts/{a}/balances",
            body={"date": "2026-09-01", "balance_gbp": 5000},
            response={"id": PHONE_ID_BASE + 2, "account_id": a},
        ),
    ]


def test_push_lands_on_the_pc_with_the_pcs_own_ids(client: TestClient, db: Session):
    _person(client, "Already on the PC")
    device, _ = devices.pair(db, "Pixel")

    results = apply.apply_ops(db, device, _phone_ops_new_account_with_balance(), app)

    assert [r.status for r in results] == ["applied"] * 3
    account = db.scalar(select(Account).where(Account.name == "Phone saver"))
    assert account is not None and account.id < PHONE_ID_BASE
    owner_ids = [o.person_id for o in account.owners]
    alex = db.scalar(select(Person).where(Person.name == "Alex"))
    assert owner_ids == [alex.id]
    entries = db.scalars(select(BalanceEntry).where(BalanceEntry.account_id == account.id)).all()
    assert [e.balance_gbp for e in entries] == [5000]


def test_resending_a_push_changes_nothing(client: TestClient, db: Session):
    device, _ = devices.pair(db, "Pixel")
    ops = _phone_ops_new_account_with_balance()
    apply.apply_ops(db, device, ops, app)
    again = apply.apply_ops(db, device, ops, app)

    assert [r.status for r in again] == ["applied"] * 3
    assert db.scalar(select(func.count()).select_from(Account)) == 1
    assert db.scalar(select(func.count()).select_from(BalanceEntry)) == 1
    assert db.scalar(select(func.count()).select_from(SyncAppliedOp)) == 3


def test_ops_that_depend_on_a_rejected_create_are_rejected(client: TestClient, db: Session):
    device, _ = devices.pair(db, "Pixel")
    ops = _phone_ops_new_account_with_balance()
    ops[1].body["valuation_method"] = "holdings"  # cash + holdings is not an allowed combination

    results = apply.apply_ops(db, device, ops, app)

    assert [r.status for r in results] == ["applied", "rejected", "rejected"]
    assert results[2].message == "Depends on an earlier change that the PC rejected"
    assert db.scalar(select(func.count()).select_from(BalanceEntry)) == 0


def test_an_impossible_sell_is_rejected_with_the_pcs_reason(client: TestClient, db: Session):
    person = _person(client)
    account = client.post(
        "/api/accounts",
        json={
            "name": "ISA",
            "category": "investment",
            "wrapper": "isa",
            "valuation_method": "holdings",
            "owners": [{"person_id": person["id"], "share": 1.0}],
        },
    ).json()
    instrument = client.post(
        "/api/instruments", json={"symbol": "MANUAL:X", "price_source": "manual", "manual_price_gbp": 10}
    ).json()
    client.post(
        f"/api/accounts/{account['id']}/transactions",
        json={"date": "2026-09-01", "type": "BUY", "instrument_id": instrument["id"], "units": 10, "amount_gbp": -100},
    )
    device, _ = devices.pair(db, "Pixel")
    sell = apply.Op(
        "op-sell",
        "POST",
        f"/api/accounts/{account['id']}/transactions",
        body={"date": "2026-09-02", "type": "SELL", "instrument_id": instrument["id"], "units": 20, "amount_gbp": 200},
    )

    [result] = apply.apply_ops(db, device, [sell], app)

    assert result.status == "rejected"
    assert result.message.startswith("There weren't enough units left on the PC")
    assert "held 10" in result.message
    assert db.scalar(select(func.count()).select_from(Transaction)) == 1


# --- the LAN listener --------------------------------------------------------------------------


@pytest.fixture()
def lan_client(db: Session) -> Iterator[TestClient]:
    lan.reset_rate_limit()
    lan.lan_app.dependency_overrides[get_db] = lambda: db
    yield TestClient(lan.lan_app)
    lan.lan_app.dependency_overrides.clear()
    lan.reset_rate_limit()


def test_sync_endpoints_need_a_paired_token(lan_client: TestClient, db: Session):
    assert lan_client.get("/sync/v1/hello").status_code == 401
    assert lan_client.get("/sync/v1/hello", headers={"Authorization": "Bearer wrong"}).status_code == 401

    device, token = devices.pair(db, "Pixel")
    ok = lan_client.get("/sync/v1/hello", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["device_id"] == device.id

    devices.unpair(db, device.id)
    assert lan_client.get("/sync/v1/hello", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_repeated_bad_tokens_lock_the_caller_out(lan_client: TestClient, db: Session):
    _, token = devices.pair(db, "Pixel")
    for _ in range(lan.MAX_FAILURES):
        lan_client.get("/sync/v1/hello", headers={"Authorization": "Bearer guess"})
    r = lan_client.get("/sync/v1/hello", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 429


def test_the_lan_app_serves_nothing_but_sync(lan_client: TestClient):
    assert lan_client.get("/api/people").status_code == 404
    assert lan_client.get("/openapi.json").status_code == 404


def test_pairing_uri_round_trips(db: Session):
    uri = devices.pairing_uri(["192.168.1.20", "10.0.0.5"], 8766, "tok-en_123", 7, "Home PC")
    cfg = client.parse_pairing_uri(uri)
    assert cfg.hosts == ["192.168.1.20", "10.0.0.5"]
    assert (cfg.port, cfg.token, cfg.device_id, cfg.pc_name) == (8766, "tok-en_123", 7, "Home PC")


def test_pairing_accepts_the_waymark_scheme_too(db: Session):
    uri = devices.pairing_uri(["192.168.1.20"], 8766, "tok", 7, "Home PC").replace("passbook://", "waymark://")
    assert client.parse_pairing_uri(uri).port == 8766


# --- end to end: two real database files --------------------------------------------------------


def _file_db(path: Path) -> tuple[sessionmaker, object]:
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        seed_service.ensure_defaults(s)
    return factory, engine


def _use_db(target_app, session: Session) -> None:  # noqa: ANN001
    target_app.dependency_overrides[get_db] = lambda: session


def test_end_to_end_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    lan.reset_rate_limit()
    app.dependency_overrides[get_price_provider] = FakeProvider
    pc_factory, pc_engine = _file_db(tmp_path / "pc.db")
    phone_file = tmp_path / "phone.db"
    phone_factory, phone_engine = _file_db(phone_file)
    pc = pc_factory()
    phone = phone_factory()
    try:
        # The PC has a person and an account, and the phone starts from a copy of it.
        _use_db(app, pc)
        web = TestClient(app)
        alex = _person(web)
        current = _cash_account(web, alex["id"])
        device, token = devices.pair(pc, "Pixel")
        phone.close()
        phone_engine.dispose()
        snapshot.make_copy(pc).replace(phone_file)
        phone = phone_factory()

        # On the phone: a balance on the existing account, and a new account with a balance.
        monkeypatch.setattr(settings, "role", "phone")
        ids.reset_counter()
        _use_db(app, phone)
        web.post(f"/api/accounts/{current['id']}/balances", json={"date": "2026-09-10", "balance_gbp": 850})
        saver = _cash_account(web, alex["id"], "Phone saver")
        assert saver["id"] >= PHONE_ID_BASE
        web.post(f"/api/accounts/{saver['id']}/balances", json={"date": "2026-09-11", "balance_gbp": 3000})
        assert outbox.pending_count(phone) == 3

        # Sync. The PC side runs as the desktop.
        monkeypatch.setattr(settings, "role", "desktop")
        _use_db(app, pc)
        _use_db(lan.lan_app, pc)
        client.save_config(client.SyncConfig(hosts=["192.168.1.20"], port=8766, token=token, device_id=device.id))

        def http(base: str, tok: str, timeout: float) -> TestClient:
            return TestClient(lan.lan_app, base_url=base, headers={"Authorization": f"Bearer {tok}"})

        report = client.sync_now(phone, http=http, db_file=phone_file, dispose=phone_engine.dispose)

        assert report["status"] == "ok"
        assert (report["applied"], report["rejected"]) == (3, [])

        # The PC has both changes, with its own ids.
        pc.expire_all()
        pc_saver = pc.scalar(select(Account).where(Account.name == "Phone saver"))
        assert pc_saver is not None and pc_saver.id < PHONE_ID_BASE
        balances = {
            (e.account_id, e.balance_gbp) for e in pc.scalars(select(BalanceEntry)).all()
        }
        assert balances == {(current["id"], 850), (pc_saver.id, 3000)}

        # The phone now holds the PC's copy: same accounts and ids, empty outbox, no pairing rows.
        phone = phone_factory()
        assert sorted(a.id for a in phone.scalars(select(Account))) == sorted(a.id for a in pc.scalars(select(Account)))
        assert phone.scalar(select(func.count()).select_from(SyncOutbox)) == 0
        assert (tmp_path / "phone.db.previous").exists()

        # Syncing again changes nothing.
        again = client.sync_now(phone, http=http, db_file=phone_file, dispose=phone_engine.dispose)
        assert (again["status"], again["applied"]) == ("ok", 0)
        pc.expire_all()
        assert pc.scalar(select(func.count()).select_from(BalanceEntry)) == 2
        assert client.load_config().last_report["applied"] == 0
    finally:
        app.dependency_overrides.clear()
        lan.lan_app.dependency_overrides.clear()
        pc.close()
        phone.close()
        pc_engine.dispose()
        phone_engine.dispose()


def test_an_unreachable_pc_leaves_the_phone_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db: Session):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    client.save_config(client.SyncConfig(hosts=["192.0.2.1"], port=8766, token="t", device_id=1))

    def http(base: str, tok: str, timeout: float):  # noqa: ANN202
        import httpx

        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        return httpx.Client(base_url=base, transport=httpx.MockTransport(refuse))

    report = client.sync_now(db, http=http, db_file=tmp_path / "unused.db", dispose=lambda: None)

    assert report == {"status": "pc_unreachable"}
    assert client.load_config().last_attempt_at is not None
