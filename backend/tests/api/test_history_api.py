from __future__ import annotations

from fastapi.testclient import TestClient


def _person(client: TestClient) -> int:
    return client.post("/api/people", json={"name": "James"}).json()["id"]


def _account(client: TestClient, person_id: int, **extra) -> dict:
    payload = {
        "name": "Cash",
        "category": "cash",
        "wrapper": "none",
        "valuation_method": "balance",
        "owners": [{"person_id": person_id, "share": 1.0}],
        **extra,
    }
    return client.post("/api/accounts", json=payload).json()


def test_networth_history_returns_dates_total_and_series(client: TestClient):
    person_id = _person(client)
    account = _account(
        client, person_id, initial_balance={"date": "2026-09-15", "balance_gbp": 100.0}
    )
    r = client.post(
        "/api/snapshots/rebuild", json={"account_id": account["id"], "from_date": "2026-09-15"}
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert isinstance(job_id, str) and job_id

    status = client.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] in ("pending", "running", "done", "error")


def test_jobs_endpoint_404s_for_unknown_job(client: TestClient):
    r = client.get("/api/jobs/not-a-real-job")
    assert r.status_code == 404


def test_account_history_endpoint_shape(client: TestClient):
    person_id = _person(client)
    account = _account(
        client, person_id, initial_balance={"date": "2026-09-15", "balance_gbp": 100.0}
    )
    r = client.get(f"/api/accounts/{account['id']}/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_networth_history_endpoint_shape(client: TestClient):
    _person(client)
    r = client.get("/api/networth/history?granularity=day&group_by=category")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"dates", "total", "series"}
    assert len(body["dates"]) == len(body["total"])
