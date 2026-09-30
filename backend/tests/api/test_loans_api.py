from __future__ import annotations

from fastapi.testclient import TestClient
from freezegun import freeze_time


def _create_mortgage(client: TestClient, person_id: int) -> dict:
    r = client.post(
        "/api/accounts",
        json={
            "name": "Mortgage",
            "category": "mortgage",
            "wrapper": "none",
            "valuation_method": "amortising",
            "owners": [{"person_id": person_id, "share": 1.0}],
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
    return r.json()


def test_schedule_endpoint_returns_the_annuity_payment(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        account = _create_mortgage(client, james["id"])
        r = client.get(f"/api/accounts/{account['id']}/schedule")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["monthly_payment_gbp"] == 1111.66
    assert len(body["rows"]) > 0


def test_simulate_endpoint_does_not_persist_anything(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        account = _create_mortgage(client, james["id"])
        r = client.post(
            f"/api/accounts/{account['id']}/schedule/simulate",
            json={"extra_monthly_gbp": 200.0, "lump_sums": []},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["months_saved"] > 0
        assert body["interest_saved_gbp"] > 0

        overpayments = client.get(f"/api/accounts/{account['id']}/overpayments").json()
        assert overpayments == []


def test_save_simulation_persists_planned_overpayments(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        account = _create_mortgage(client, james["id"])
        r = client.post(
            f"/api/accounts/{account['id']}/schedule/simulate/save",
            json={"extra_monthly_gbp": 200.0, "lump_sums": []},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()) > 0

        overpayments = client.get(f"/api/accounts/{account['id']}/overpayments").json()
        assert len(overpayments) > 0
        assert all(o["is_planned"] for o in overpayments)


def test_rate_period_overlap_returns_422(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        account = _create_mortgage(client, james["id"])
        r = client.post(
            f"/api/accounts/{account['id']}/rate-periods",
            json={"start_date": "2027-01-01", "end_date": "2029-01-01", "annual_rate": 0.05, "rate_type": "fixed"},
        )
    assert r.status_code == 422
    assert r.json()["error"]["field"] == "rate_periods"


def test_equity_endpoint_for_a_property_with_a_secured_mortgage(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        prop = client.post(
            "/api/accounts",
            json={
                "name": "Home",
                "category": "property",
                "wrapper": "none",
                "valuation_method": "model",
                "owners": [{"person_id": james["id"], "share": 1.0}],
                "initial_balance": {"date": "2026-09-01", "balance_gbp": 400000},
                "growth_model": {"annual_rate": 0.0, "method": "compound"},
                "property": {"purchase_date": "2026-09-01", "purchase_price_gbp": 400000},
            },
        ).json()
        account = _create_mortgage(client, james["id"])
        client.put(
            f"/api/accounts/{account['id']}/loan",
            json={
                "secured_on_account_id": prop["id"],
                "original_amount_gbp": 200000,
                "start_date": "2026-09-01",
                "maturity_date": "2051-09-01",
                "fallback_rate": 0.045,
            },
        )

        r = client.get(f"/api/accounts/{prop['id']}/equity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value_gbp"] == 400000.0
    assert body["equity_gbp"] == 200000.0
    assert body["ltv"] == 0.5
