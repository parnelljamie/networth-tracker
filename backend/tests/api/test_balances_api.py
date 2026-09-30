from __future__ import annotations

from fastapi.testclient import TestClient


def _person(client: TestClient) -> int:
    return client.post("/api/people", json={"name": "James"}).json()["id"]


def _account(client: TestClient, person_id: int, category: str, method: str, **extra) -> dict:
    payload = {
        "name": "Test account",
        "category": category,
        "wrapper": "none",
        "valuation_method": method,
        "owners": [{"person_id": person_id, "share": 1.0}],
        **extra,
    }
    return client.post("/api/accounts", json=payload).json()


def test_bulk_balances_upserts_and_networth_reflects_it_immediately(client: TestClient):
    person_id = _person(client)
    cash = _account(
        client, person_id, "cash", "balance", initial_balance={"date": "2026-09-15", "balance_gbp": 100.0}
    )
    other = _account(
        client,
        person_id,
        "other_liability",
        "balance",
        initial_balance={"date": "2026-09-15", "balance_gbp": 50.0},
    )
    third = _account(client, person_id, "cash", "balance")

    r = client.post(
        "/api/balances/bulk",
        json={
            "entries": [
                {"account_id": cash["id"], "date": "2026-09-15", "balance_gbp": 200.0},
                {"account_id": other["id"], "date": "2026-09-15", "balance_gbp": 75.0},
                {"account_id": third["id"], "date": "2026-09-15", "balance_gbp": 30.0},
            ]
        },
    )
    assert r.status_code == 200
    assert r.json() == {"saved": 3}

    household = client.get("/api/networth/current").json()
    # 200 (cash) + 30 (cash) - 75 (liability) = 155
    assert household["total_gbp"] == 155.0


def test_quick_update_lists_only_balance_style_accounts(client: TestClient):
    _account(client, _person(client), "cash", "balance")
    r = client.get("/api/balances/quick-update")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["last_date"] is None
    assert rows[0]["staleness"] == "alert"


def test_upsert_balance_on_same_date_updates_in_place(client: TestClient):
    account = _account(client, _person(client), "cash", "balance")
    r1 = client.post(
        f"/api/accounts/{account['id']}/balances", json={"date": "2026-09-15", "balance_gbp": 100.0}
    )
    r2 = client.post(
        f"/api/accounts/{account['id']}/balances", json={"date": "2026-09-15", "balance_gbp": 250.0}
    )
    assert r1.json()["id"] == r2.json()["id"]

    balances = client.get(f"/api/accounts/{account['id']}/balances").json()
    assert len(balances) == 1
    assert balances[0]["balance_gbp"] == 250.0
