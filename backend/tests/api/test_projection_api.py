from __future__ import annotations

from fastapi.testclient import TestClient
from freezegun import freeze_time


def test_scenarios_are_seeded(client: TestClient):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert names == {"Base", "Optimistic", "Pessimistic"}
    base = next(s for s in r.json() if s["name"] == "Base")
    assert base["is_default"] is True
    optimistic = next(s for s in r.json() if s["name"] == "Optimistic")
    assert optimistic["return_adjustment"] == 0.02
    pessimistic = next(s for s in r.json() if s["name"] == "Pessimistic")
    assert pessimistic["return_adjustment"] == -0.02


def test_cannot_delete_default_scenario(client: TestClient):
    scenarios = client.get("/api/scenarios").json()
    base = next(s for s in scenarios if s["name"] == "Base")
    r = client.delete(f"/api/scenarios/{base['id']}")
    assert r.status_code == 422


def test_projection_endpoint_and_scenario_comparison(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        client.post(
            "/api/accounts",
            json={
                "name": "ISA",
                "category": "investment",
                "wrapper": "isa",
                "valuation_method": "balance",
                "owners": [{"person_id": james["id"], "share": 1.0}],
                "expected_return_rate": 0.05,
                "initial_balance": {"date": "2026-01-01", "balance_gbp": 10000.0},
            },
        )

        r = client.get("/api/projection", params={"months": 240})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"][0] == 10000.0
        assert len(body["dates"]) == 241

        scenarios = {s["name"]: s["id"] for s in client.get("/api/scenarios").json()}
        r = client.post(
            "/api/projection/compare",
            json={
                "scenario_ids": [scenarios["Optimistic"], scenarios["Base"], scenarios["Pessimistic"]],
                "months": 240,
            },
        )
        assert r.status_code == 200, r.text
        compare = r.json()
        by_name = {s["name"]: s["total"][-1] for s in compare["series"]}
        assert by_name["Optimistic"] > by_name["Base"] > by_name["Pessimistic"]


def test_lump_sum_scenario_event_lifts_the_line(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    with freeze_time("2026-09-16"):
        account = client.post(
            "/api/accounts",
            json={
                "name": "ISA",
                "category": "investment",
                "wrapper": "isa",
                "valuation_method": "balance",
                "owners": [{"person_id": james["id"], "share": 1.0}],
                "expected_return_rate": 0.0,
                "initial_balance": {"date": "2026-01-01", "balance_gbp": 10000.0},
            },
        ).json()

        scenario = client.post("/api/scenarios", json={"name": "Lump sum test"}).json()
        r = client.post(
            f"/api/scenarios/{scenario['id']}/events",
            json={
                "date": "2030-01-01",
                "kind": "lump_sum",
                "account_id": account["id"],
                "amount_gbp": 10000.0,
                "label": "Inheritance",
            },
        )
        assert r.status_code == 201, r.text

        r = client.get("/api/projection", params={"scenario_id": scenario["id"], "months": 60})
        body = r.json()
        event_index = next(i for i, d in enumerate(body["dates"]) if d >= "2030-01-01")
        before = body["total"][event_index - 1]
        after = body["total"][event_index]
        assert after - before >= 9000  # lump sum landed

        milestone_kinds = {m["kind"] for m in body["milestones"]}
        assert "scenario_event" in milestone_kinds


def test_monte_carlo_band_brackets_the_projection(client: TestClient):
    james = client.post("/api/people", json={"name": "James"}).json()
    owners = [{"person_id": james["id"], "share": 1.0}]
    with freeze_time("2026-09-16"):
        client.post(
            "/api/accounts",
            json={
                "name": "ISA",
                "category": "investment",
                "wrapper": "isa",
                "valuation_method": "balance",
                "owners": owners,
                "expected_return_rate": 0.05,
                "initial_balance": {"date": "2026-09-01", "balance_gbp": 10000.0},
            },
        )
        client.post(
            "/api/accounts",
            json={
                "name": "Savings",
                "category": "cash",
                "valuation_method": "balance",
                "owners": owners,
                "initial_balance": {"date": "2026-09-01", "balance_gbp": 5000.0},
            },
        )

        r = client.get("/api/projection/monte-carlo", params={"months": 120})
        assert r.status_code == 200, r.text
        body = r.json()
        det = client.get("/api/projection", params={"months": 120}).json()

        assert body["dates"] == det["dates"]
        assert body["deterministic"] == det["total"]
        assert body["paths"] == 1000
        assert body["p10"][0] == body["p90"][0] == 15000.0
        last = -1
        assert body["p10"][last] < body["p25"][last] < body["p50"][last] < body["p75"][last] < body["p90"][last]
        assert body["p10"][last] < det["total"][last] < body["p90"][last]
        # Cash is deterministic, so even the worst decile keeps the savings pot.
        assert body["p10"][last] > 5000.0

        # Stable between calls (fixed seed, cached).
        assert client.get("/api/projection/monte-carlo", params={"months": 120}).json() == body


def test_monte_carlo_rejects_an_unbounded_horizon(client: TestClient):
    assert client.get("/api/projection/monte-carlo", params={"months": 10_000}).status_code == 422
