from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_list_people(client: TestClient):
    r = client.post("/api/people", json={"name": "James", "color": "#2a78d6"})
    assert r.status_code == 201, r.text
    r = client.post("/api/people", json={"name": "Sam", "color": "#eb6834"})
    assert r.status_code == 201, r.text

    r = client.get("/api/people")
    names = {p["name"] for p in r.json()}
    assert names == {"James", "Sam"}


def test_delete_person_who_owns_an_account_is_a_conflict(client: TestClient):
    person = client.post("/api/people", json={"name": "James"}).json()
    client.post(
        "/api/accounts",
        json={
            "name": "Cash",
            "category": "cash",
            "wrapper": "none",
            "valuation_method": "balance",
            "owners": [{"person_id": person["id"], "share": 1.0}],
        },
    )
    r = client.delete(f"/api/people/{person['id']}")
    assert r.status_code == 409
    # Archiving is no longer offered in the UI, so the refusal must not point at it.
    assert "rchive" not in r.text


def test_delete_person_without_accounts_succeeds(client: TestClient):
    person = client.post("/api/people", json={"name": "Solo"}).json()
    r = client.delete(f"/api/people/{person['id']}")
    assert r.status_code == 204
