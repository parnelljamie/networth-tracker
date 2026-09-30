from __future__ import annotations

from fastapi.testclient import TestClient


def test_goal_api_crud(client: TestClient):
    client.post("/api/people", json={"name": "James"})
    r = client.post("/api/goals", json={"name": "Rainy day", "target_gbp": 1000, "scope": "household"})
    assert r.status_code == 201, r.text
    goal = r.json()
    assert "progress" in goal and "current_value_gbp" in goal and "projected_hit_date" in goal

    r = client.get("/api/goals")
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.patch(f"/api/goals/{goal['id']}", json={"target_gbp": 2000})
    assert r.status_code == 200 and r.json()["target_gbp"] == 2000

    r = client.delete(f"/api/goals/{goal['id']}")
    assert r.status_code == 204


def test_insights_api(client: TestClient):
    r = client.get("/api/insights/attribution", params={"start": "2026-01-01", "end": "2026-02-01"})
    assert r.status_code == 200, r.text
    body = r.json()
    expected_fields = {
        "contributions_gbp",
        "market_gbp",
        "mortgage_paid_gbp",
        "revaluation_gbp",
        "other_gbp",
        "total_gbp",
        "start_total_gbp",
        "end_total_gbp",
    }
    assert expected_fields.issubset(body)

    r = client.get("/api/insights/deposit-protection")
    assert r.status_code == 200
    assert "entries" in r.json()


def test_export_and_account_xirr_api(client: TestClient):
    r = client.get("/api/export")
    assert r.status_code == 200
    assert "people" in r.json()

    james = client.post("/api/people", json={"name": "James"}).json()
    account = client.post(
        "/api/accounts",
        json={
            "name": "ISA",
            "category": "investment",
            "wrapper": "isa",
            "valuation_method": "holdings",
            "owners": [{"person_id": james["id"], "share": 1.0}],
        },
    ).json()
    r = client.get(f"/api/accounts/{account['id']}/xirr")
    assert r.status_code == 200
    assert r.json() == {"xirr": None, "annualised": True, "since": None}
