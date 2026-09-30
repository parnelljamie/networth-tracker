from __future__ import annotations

from fastapi.testclient import TestClient


def _account(client: TestClient) -> int:
    person = client.post("/api/people", json={"name": "James"}).json()
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
    return account["id"]


def _instrument(client: TestClient, price: float = 10.0) -> int:
    return client.post(
        "/api/instruments",
        json={"symbol": "MANUAL:X", "price_source": "manual", "manual_price_gbp": price},
    ).json()["id"]


def test_set_holding_then_holdings_reflects_it(client: TestClient):
    account_id = _account(client)
    instrument_id = _instrument(client, price=10.0)

    r = client.put(
        f"/api/accounts/{account_id}/holdings/{instrument_id}", json={"units": 100, "avg_cost_gbp": 8.0}
    )
    assert r.status_code == 200
    holdings = r.json()
    assert holdings["positions"][0]["units"] == 100
    assert holdings["positions"][0]["value_gbp"] == 1000.0  # 100 * manual price 10.0


def test_set_cash_creates_adjustment(client: TestClient):
    account_id = _account(client)
    r = client.put(f"/api/accounts/{account_id}/cash", json={"cash_gbp": 500.0})
    assert r.status_code == 200
    assert r.json()["cash_gbp"] == 500.0


def test_oversell_returns_422_with_readable_message(client: TestClient):
    account_id = _account(client)
    instrument_id = _instrument(client)
    client.post(
        f"/api/accounts/{account_id}/transactions",
        json={"date": "2026-09-01", "type": "BUY", "instrument_id": instrument_id, "units": 10, "amount_gbp": -100},
    )
    r = client.post(
        f"/api/accounts/{account_id}/transactions",
        json={"date": "2026-09-02", "type": "SELL", "instrument_id": instrument_id, "units": 20, "amount_gbp": 200},
    )
    assert r.status_code == 422
    assert "held 10" in r.json()["error"]["message"]


def test_delete_transaction_rebuilds_positions(client: TestClient):
    account_id = _account(client)
    instrument_id = _instrument(client)
    txn = client.post(
        f"/api/accounts/{account_id}/transactions",
        json={"date": "2026-09-01", "type": "BUY", "instrument_id": instrument_id, "units": 10, "amount_gbp": -100},
    ).json()

    client.delete(f"/api/transactions/{txn['id']}")

    holdings = client.get(f"/api/accounts/{account_id}/holdings").json()
    assert holdings["positions"] == []


def test_transactions_list_paginated(client: TestClient):
    account_id = _account(client)
    instrument_id = _instrument(client)
    for i in range(3):
        client.post(
            f"/api/accounts/{account_id}/transactions",
            json={
                "date": f"2026-09-0{i + 1}",
                "type": "BUY",
                "instrument_id": instrument_id,
                "units": 1,
                "amount_gbp": -10,
            },
        )
    r = client.get(f"/api/accounts/{account_id}/transactions", params={"limit": 2})
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
