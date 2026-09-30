from __future__ import annotations

from fastapi.testclient import TestClient

from app.providers.base import InstrumentMetadata
from tests.fakes import FakeProvider


def test_create_manual_instrument(client: TestClient):
    r = client.post(
        "/api/instruments",
        json={"symbol": "MANUAL:GOLD", "price_source": "manual", "name": "Gold", "manual_price_gbp": 1800.0},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["price_source"] == "manual"
    assert body["manual_price_gbp"] == 1800.0


def test_create_yahoo_instrument_fetches_metadata(client: TestClient, fake_provider: FakeProvider):
    fake_provider.set_metadata(
        "VUSA.L", InstrumentMetadata(name="Vanguard S&P 500", currency="GBp", exchange="LSE", quote_type="ETF")
    )
    r = client.post("/api/instruments", json={"symbol": "VUSA.L", "price_source": "yahoo"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Vanguard S&P 500"
    assert body["quote_currency"] == "GBp"
    assert body["exchange"] == "LSE"


def test_create_instrument_with_existing_symbol_returns_existing_row(client: TestClient):
    r1 = client.post(
        "/api/instruments",
        json={"symbol": "MANUAL:GOLD", "price_source": "manual", "manual_price_gbp": 1800.0},
    )
    r2 = client.post(
        "/api/instruments",
        json={"symbol": "MANUAL:GOLD", "price_source": "manual", "manual_price_gbp": 1900.0},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json()["manual_price_gbp"] == 1800.0  # unchanged — returned the existing row


def test_search_uses_provider(client: TestClient, fake_provider: FakeProvider):
    from app.providers.base import InstrumentSearchResult

    fake_provider.set_search_results(
        [InstrumentSearchResult(symbol="AAPL", name="Apple Inc.", exchange="NMS", quote_type="EQUITY")]
    )
    r = client.get("/api/instruments/search", params={"q": "apple"})
    assert r.status_code == 200
    assert r.json()[0]["symbol"] == "AAPL"
