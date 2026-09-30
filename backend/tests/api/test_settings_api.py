from __future__ import annotations

from fastapi.testclient import TestClient


def test_settings_seeded_with_defaults(client: TestClient):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["inflation_rate"] == 0.025
    assert body["stale_balance_days"] == {"warn": 35, "alert": 90}


def test_patch_settings_updates_one_key(client: TestClient):
    r = client.patch("/api/settings", json={"inflation_rate": 0.03})
    assert r.status_code == 200
    assert r.json()["inflation_rate"] == 0.03
    assert client.get("/api/settings").json()["inflation_rate"] == 0.03


def test_patch_settings_rejects_unknown_key(client: TestClient):
    r = client.patch("/api/settings", json={"not_a_real_setting": 1})
    assert r.status_code == 422


def test_tax_year_rules_seeded_for_2024_to_2026(client: TestClient):
    r = client.get("/api/tax-year-rules")
    years = {row["tax_year_start"] for row in r.json()}
    assert years == {2024, 2025, 2026}
