from __future__ import annotations

from fastapi.testclient import TestClient


def _create_people(client: TestClient) -> tuple[int, int]:
    james = client.post("/api/people", json={"name": "James"}).json()
    sam = client.post("/api/people", json={"name": "Sam"}).json()
    return james["id"], sam["id"]


def test_joint_current_account_splits_50_50(client: TestClient):
    james_id, sam_id = _create_people(client)
    r = client.post(
        "/api/accounts",
        json={
            "name": "Joint Current Account",
            "category": "cash",
            "wrapper": "none",
            "valuation_method": "balance",
            "owners": [{"person_id": james_id, "share": 0.5}, {"person_id": sam_id, "share": 0.5}],
            "initial_balance": {"date": "2026-09-15", "balance_gbp": 2000.0},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["value_gbp"] == 2000.0

    household = client.get("/api/networth/current").json()
    assert household["total_gbp"] == 2000.0
    by_person = {p["person_id"]: p["value_gbp"] for p in household["by_person"]}
    assert by_person[james_id] == 1000.0
    assert by_person[sam_id] == 1000.0

    james_scope = client.get(f"/api/networth/current?person_id={james_id}").json()
    assert james_scope["total_gbp"] == 1000.0


def test_isa_with_two_owners_is_rejected(client: TestClient):
    james_id, sam_id = _create_people(client)
    r = client.post(
        "/api/accounts",
        json={
            "name": "Joint ISA",
            "category": "investment",
            "wrapper": "isa",
            "valuation_method": "balance",
            "owners": [{"person_id": james_id, "share": 0.5}, {"person_id": sam_id, "share": 0.5}],
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation"
    assert body["error"]["field"] == "owners"


def test_credit_card_lowers_net_worth_and_is_flagged_a_liability(client: TestClient):
    james_id, _ = _create_people(client)
    r = client.post(
        "/api/accounts",
        json={
            "name": "Amex",
            "category": "credit_card",
            "wrapper": "none",
            "valuation_method": "balance",
            "owners": [{"person_id": james_id, "share": 1.0}],
            "initial_balance": {"date": "2026-09-15", "balance_gbp": 500.0},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["value_gbp"] == -500.0
    assert body["is_liability"] is True

    household = client.get("/api/networth/current").json()
    assert household["total_gbp"] == -500.0
    assert household["liabilities_gbp"] == -500.0


def test_account_excluded_from_networth_still_listed_but_not_totalled(client: TestClient):
    james_id, _ = _create_people(client)
    client.post(
        "/api/accounts",
        json={
            "name": "Untracked cash",
            "category": "cash",
            "wrapper": "none",
            "valuation_method": "balance",
            "owners": [{"person_id": james_id, "share": 1.0}],
            "include_in_networth": False,
            "initial_balance": {"date": "2026-09-15", "balance_gbp": 999.0},
        },
    )
    household = client.get("/api/networth/current").json()
    assert household["total_gbp"] == 0.0
    assert len(household["accounts"]) == 1


def test_archived_account_excluded_from_default_list_and_networth(client: TestClient):
    james_id, _ = _create_people(client)
    account = client.post(
        "/api/accounts",
        json={
            "name": "Old ISA",
            "category": "investment",
            "wrapper": "isa",
            "valuation_method": "balance",
            "owners": [{"person_id": james_id, "share": 1.0}],
            "initial_balance": {"date": "2026-09-15", "balance_gbp": 5000.0},
        },
    ).json()

    client.post(f"/api/accounts/{account['id']}/archive")

    assert client.get("/api/accounts").json() == []
    household = client.get("/api/networth/current").json()
    assert household["total_gbp"] == 0.0
