from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "imports"


@pytest.fixture()
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Import uploads are written under settings.data_dir — keep them out of the real data dir."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def _person(client: TestClient) -> int:
    return client.post("/api/people", json={"name": "James"}).json()["id"]


def _holdings_account(client: TestClient, person_id: int) -> int:
    return client.post(
        "/api/accounts",
        json={
            "name": "ISA",
            "category": "investment",
            "wrapper": "isa",
            "valuation_method": "holdings",
            "owners": [{"person_id": person_id, "share": 1.0}],
        },
    ).json()["id"]


def _cash_account(client: TestClient, person_id: int) -> int:
    return client.post(
        "/api/accounts",
        json={
            "name": "Current Account",
            "category": "cash",
            "wrapper": "none",
            "valuation_method": "balance",
            "owners": [{"person_id": person_id, "share": 1.0}],
        },
    ).json()["id"]


def _instrument(client: TestClient, symbol: str = "VUSA.L", isin: str = "IE00B3XXRP09") -> int:
    return client.post(
        "/api/instruments",
        json={"symbol": symbol, "price_source": "manual", "manual_price_gbp": 70.0},
    ).json()["id"]


def _upload(client: TestClient, kind: str, account_id: int, fixture_name: str) -> dict:
    path = FIXTURES / fixture_name
    with open(path, "rb") as f:
        r = client.post(
            "/api/imports",
            data={"kind": kind, "account_id": str(account_id)},
            files={"file": (fixture_name, f, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/imports/jobs/{job_id}").json()
        if status["status"] in ("done", "error"):
            return status
        time.sleep(0.05)
    raise AssertionError("rebuild job did not finish in time")


# ---------------------------------------------------------------------------
# Canonical CSV import + reconciliation
# ---------------------------------------------------------------------------


def test_canonical_csv_imports_with_correct_reconciliation(client: TestClient, isolated_data_dir: Path):
    person_id = _person(client)
    account_id = _holdings_account(client, person_id)
    _instrument(client)

    upload = _upload(client, "transactions", account_id, "canonical_transactions.csv")
    assert upload["headers"][:2] == ["date", "type"]
    batch_id = upload["batch"]["id"]

    preview = client.post(f"/api/imports/{batch_id}/preview", json={}).json()
    assert preview["ready"] is True
    assert preview["unmatched_instruments"] == []
    assert preview["counts_by_type"] == {"DEPOSIT": 1, "BUY": 1, "DIVIDEND": 1}

    recon = {r["symbol"]: r for r in preview["reconciliation"] if r["symbol"]}
    row = recon["VUSA.L"]
    assert row["current_units"] == 0.0
    assert row["imported_units"] == 300.0
    assert row["imported_avg_cost_gbp"] == pytest.approx(65.12, abs=0.01)


def test_commit_replaces_stand_ins_and_extends_history(client: TestClient, isolated_data_dir: Path):
    person_id = _person(client)
    account_id = _holdings_account(client, person_id)
    instrument_id = _instrument(client)

    # A quick-entry stand-in the user made before ever importing history: 100 units @ £60.
    client.put(
        f"/api/accounts/{account_id}/holdings/{instrument_id}",
        json={"units": 100, "avg_cost_gbp": 60.0, "as_of": "2026-01-01"},
    )
    holdings_before = client.get(f"/api/accounts/{account_id}/holdings").json()
    assert holdings_before["positions"][0]["units"] == 100

    upload = _upload(client, "transactions", account_id, "canonical_transactions.csv")
    batch_id = upload["batch"]["id"]
    client.post(f"/api/imports/{batch_id}/preview", json={})

    r = client.post(
        f"/api/imports/{batch_id}/commit",
        json={"replace_stand_ins": True, "align_to_current": False},
    )
    assert r.status_code == 200, r.text
    commit_body = r.json()
    assert commit_body["batch"]["status"] == "committed"
    _wait_for_job(client, commit_body["job_id"])

    holdings_after = client.get(f"/api/accounts/{account_id}/holdings").json()
    positions = {p["instrument"]["id"]: p for p in holdings_after["positions"]}
    # The £60/100-unit stand-in is gone; only the imported 300 units @ £65.12 remain.
    assert positions[instrument_id]["units"] == 300
    assert positions[instrument_id]["avg_cost_gbp"] == pytest.approx(65.12, abs=0.01)

    txns = client.get(f"/api/accounts/{account_id}/transactions", params={"limit": 100}).json()["items"]
    assert all(t["type"] != "OPENING_BALANCE" or t["source"] != "opening" for t in txns)

    detail = client.get(f"/api/accounts/{account_id}").json()
    assert detail["value_gbp"] > 0


def test_commit_then_synchronous_rebuild_extends_history_chart(
    client: TestClient, isolated_data_dir: Path, db, monkeypatch: pytest.MonkeyPatch
):
    """The "rebuild history" step (docs/06-imports-future.md step 8) runs in a background
    thread against its own DB session — see services/importers/service.py's `start_rebuild_job`,
    the same pattern app/services/snapshot_service.py already uses for `request_rebuild`. Like
    tests/services/test_snapshot_service.py, we replace it with a synchronous call against the
    test's own in-memory session so the assertion doesn't race a real background thread that (in
    this test harness only, not the real app) points at a different, on-disk database."""
    from app.services.importers import service as import_service

    def fake_start_rebuild_job(account_id, from_date, provider=None):
        import_service.snapshot_service.rebuild(db, account_id, from_date)
        job_id = "sync-job"
        import_service._jobs[job_id] = import_service.JobStatus(status="done", progress=1.0)
        return job_id

    monkeypatch.setattr(import_service, "start_rebuild_job", fake_start_rebuild_job)

    person_id = _person(client)
    account_id = _holdings_account(client, person_id)
    _instrument(client)

    upload = _upload(client, "transactions", account_id, "canonical_transactions.csv")
    batch_id = upload["batch"]["id"]
    client.post(f"/api/imports/{batch_id}/preview", json={})
    client.post(f"/api/imports/{batch_id}/commit", json={})

    account_history = client.get(
        f"/api/accounts/{account_id}/history",
        params={"date_from": "2021-04-01", "date_to": "2021-07-01"},
    )
    assert account_history.status_code == 200
    points = account_history.json()
    assert len(points) > 0
    assert points[0]["date"] <= "2021-04-06"


def test_dedupe_skips_previously_imported_rows(client: TestClient, isolated_data_dir: Path):
    person_id = _person(client)
    account_id = _holdings_account(client, person_id)
    _instrument(client)

    upload = _upload(client, "transactions", account_id, "canonical_transactions.csv")
    batch_id = upload["batch"]["id"]
    client.post(f"/api/imports/{batch_id}/preview", json={})
    commit = client.post(f"/api/imports/{batch_id}/commit", json={}).json()
    _wait_for_job(client, commit["job_id"])

    # Re-import the same account's history plus one genuinely new row.
    upload2 = _upload(client, "transactions", account_id, "canonical_transactions_extra.csv")
    batch_id2 = upload2["batch"]["id"]
    preview2 = client.post(f"/api/imports/{batch_id2}/preview", json={}).json()
    assert preview2["batch"]["rows_imported"] == 1  # only ext-4 is new

    commit2 = client.post(
        f"/api/imports/{batch_id2}/commit", json={"replace_stand_ins": False}
    ).json()
    _wait_for_job(client, commit2["job_id"])
    assert commit2["batch"]["rows_imported"] == 1

    holdings = client.get(f"/api/accounts/{account_id}/holdings").json()
    # 300 (first import) + 50 (only new row) = 350
    assert holdings["positions"][0]["units"] == 350


def test_rollback_restores_previous_holdings_and_history(client: TestClient, isolated_data_dir: Path):
    person_id = _person(client)
    account_id = _holdings_account(client, person_id)
    instrument_id = _instrument(client)

    client.put(
        f"/api/accounts/{account_id}/holdings/{instrument_id}",
        json={"units": 100, "avg_cost_gbp": 60.0, "as_of": "2026-01-01"},
    )

    upload = _upload(client, "transactions", account_id, "canonical_transactions.csv")
    batch_id = upload["batch"]["id"]
    client.post(f"/api/imports/{batch_id}/preview", json={})
    commit = client.post(f"/api/imports/{batch_id}/commit", json={"replace_stand_ins": True}).json()
    _wait_for_job(client, commit["job_id"])

    holdings_after_commit = client.get(f"/api/accounts/{account_id}/holdings").json()
    assert holdings_after_commit["positions"][0]["units"] == 300

    r = client.post(f"/api/imports/{batch_id}/rollback")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rolled_back"

    holdings_after_rollback = client.get(f"/api/accounts/{account_id}/holdings").json()
    assert holdings_after_rollback["positions"][0]["units"] == 100
    assert holdings_after_rollback["positions"][0]["avg_cost_gbp"] == pytest.approx(60.0, abs=0.01)

    txns = client.get(f"/api/accounts/{account_id}/transactions", params={"limit": 100}).json()["items"]
    assert all(t["source"] != "import" for t in txns)


# ---------------------------------------------------------------------------
# Bank CSV -> daily balances
# ---------------------------------------------------------------------------


def test_newest_first_bank_csv_produces_correct_daily_balances(client: TestClient, isolated_data_dir: Path):
    person_id = _person(client)
    account_id = _cash_account(client, person_id)

    upload = _upload(client, "balances", account_id, "bank_running_balance_newest_first.csv")
    batch_id = upload["batch"]["id"]

    preview = client.post(f"/api/imports/{batch_id}/preview", json={}).json()
    assert preview["ready"] is True

    commit = client.post(f"/api/imports/{batch_id}/commit", json={}).json()
    assert commit["batch"]["status"] == "committed"
    _wait_for_job(client, commit["job_id"])

    balances = client.get(f"/api/accounts/{account_id}/balances").json()
    by_date = {b["date"]: b["balance_gbp"] for b in balances}
    assert by_date["2024-01-05"] == 995.0
    assert by_date["2024-01-03"] == 1015.0
    assert by_date["2024-01-01"] == 980.0


def test_bank_csv_walkback_requires_anchor_then_computes_history(client: TestClient, isolated_data_dir: Path):
    person_id = _person(client)
    account_id = _cash_account(client, person_id)

    upload = _upload(client, "balances", account_id, "bank_walkback.csv")
    batch_id = upload["batch"]["id"]

    preview_no_anchor = client.post(f"/api/imports/{batch_id}/preview", json={}).json()
    assert preview_no_anchor["ready"] is False

    preview = client.post(
        f"/api/imports/{batch_id}/preview",
        json={"anchor_balance_gbp": 900.0, "anchor_date": "2024-02-05"},
    ).json()
    assert preview["ready"] is True

    commit = client.post(
        f"/api/imports/{batch_id}/commit",
        json={"anchor_balance_gbp": 900.0, "anchor_date": "2024-02-05"},
    ).json()
    _wait_for_job(client, commit["job_id"])

    balances = client.get(f"/api/accounts/{account_id}/balances").json()
    by_date = {b["date"]: b["balance_gbp"] for b in balances}
    assert by_date["2024-02-05"] == 900.0
    assert by_date["2024-02-03"] == 940.0
    assert by_date["2024-02-01"] == 840.0
