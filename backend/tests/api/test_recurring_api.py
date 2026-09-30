from __future__ import annotations

from fastapi.testclient import TestClient
from freezegun import freeze_time


def test_create_plan_list_upcoming_and_delete(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
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

        r = client.post(
            "/api/recurring",
            json={
                "account_id": account["id"],
                "name": "Monthly ISA",
                "kind": "contribution",
                "amount_gbp": 500.0,
                "frequency": "monthly",
                "start_date": "2026-09-01",
                "auto_record": True,
            },
        )
        assert r.status_code == 201, r.text
        plan = r.json()
        assert plan["next_date"] == "2026-10-01"

        r = client.get("/api/recurring", params={"account_id": account["id"]})
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.get("/api/recurring/upcoming", params={"days": 60})
        assert r.status_code == 200
        assert any(item["plan_id"] == plan["id"] for item in r.json())

        r = client.patch(f"/api/recurring/{plan['id']}", json={"amount_gbp": 600.0})
        assert r.status_code == 200
        assert r.json()["amount_gbp"] == 600.0

        r = client.delete(f"/api/recurring/{plan['id']}")
        assert r.status_code == 204

        r = client.get("/api/recurring", params={"account_id": account["id"]})
        assert r.json() == []


def test_upcoming_includes_scheduled_mortgage_payments(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    other = client.post("/api/people", json={"name": "Other"}).json()
    with freeze_time("2026-09-16"):
        r = client.post(
            "/api/accounts",
            json={
                "name": "Mortgage",
                "category": "mortgage",
                "wrapper": "none",
                "valuation_method": "amortising",
                "owners": [{"person_id": james["id"], "share": 1.0}],
                "loan": {
                    "original_amount_gbp": 200000,
                    "start_date": "2026-09-01",
                    "maturity_date": "2051-09-01",
                    "fallback_rate": 0.045,
                    "rate_periods": [
                        {"start_date": "2026-09-01", "end_date": None, "annual_rate": 0.045, "rate_type": "fixed"}
                    ],
                },
            },
        )
        assert r.status_code == 201, r.text
        mortgage = r.json()

        r = client.get("/api/recurring/upcoming", params={"days": 60})
        assert r.status_code == 200, r.text
        payments = [i for i in r.json() if i["account_id"] == mortgage["id"]]
        assert [p["date"] for p in payments] == ["2026-10-01", "2026-11-01"]
        assert all(p["kind"] == "loan_payment" and p["plan_id"] is None for p in payments)
        assert payments[0]["gross_amount_gbp"] == 1111.66
        assert payments[0]["name"] == "Mortgage payment"

        r = client.get("/api/recurring/upcoming", params={"days": 60, "person_id": other["id"]})
        assert r.json() == []


def test_allowances_endpoint_returns_a_row_per_person(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        client.post(
            "/api/accounts",
            json={
                "name": "S&S ISA",
                "category": "investment",
                "wrapper": "isa",
                "valuation_method": "holdings",
                "owners": [{"person_id": james["id"], "share": 1.0}],
            },
        )
        r = client.get("/api/allowances", params={"person_id": james["id"]})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["person_id"] == james["id"]
        assert rows[0]["isa_limit"] == 20000.0
