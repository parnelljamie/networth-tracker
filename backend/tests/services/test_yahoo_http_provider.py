"""The phone's Yahoo provider, against canned responses in Yahoo's chart/search format."""
from __future__ import annotations

from datetime import UTC, date, datetime

import httpx

from app.providers.yahoo_http import YahooHttpProvider


def _ts(d: date, hour_utc: int = 7) -> int:
    return int(datetime(d.year, d.month, d.day, hour_utc, tzinfo=UTC).timestamp())


def _chart(symbol: str, bars: list[tuple[date, float | None]], currency: str = "GBp") -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": currency,
                        "symbol": symbol,
                        "exchangeName": "LSE",
                        "instrumentType": "ETF",
                        "longName": "Vanguard FTSE All-World UCITS ETF",
                        "gmtoffset": 3600,
                    },
                    "timestamp": [_ts(d) for d, _ in bars],
                    "indicators": {"quote": [{"close": [c for _, c in bars]}]},
                }
            ],
            "error": None,
        }
    }


def _provider(handler) -> YahooHttpProvider:  # noqa: ANN001
    return YahooHttpProvider(httpx.Client(transport=httpx.MockTransport(handler)))


def test_quotes_take_the_last_two_non_empty_bars():
    bars = [(date(2026, 9, 16), 11000.0), (date(2026, 9, 17), 11050.0), (date(2026, 9, 18), None), (date(2026, 9, 18), 11102.5)]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_chart("VWRL.L", bars))

    quotes = _provider(handler).quotes(["VWRL.L"])

    assert quotes["VWRL.L"].last == 11102.5
    assert quotes["VWRL.L"].prev_close == 11050.0
    assert quotes["VWRL.L"].bar_date == date(2026, 9, 18)
    assert seen[0].url.path == "/v8/finance/chart/VWRL.L"
    assert seen[0].url.params["range"] == "5d"


def test_a_failing_symbol_does_not_stop_the_others():
    def handler(request: httpx.Request) -> httpx.Response:
        if "BAD" in request.url.path:
            return httpx.Response(404, json={"chart": {"result": None, "error": {"code": "Not Found"}}})
        return httpx.Response(200, json=_chart("VWRL.L", [(date(2026, 9, 18), 100.0)]))

    quotes = _provider(handler).quotes(["BAD", "VWRL.L"])

    assert list(quotes) == ["VWRL.L"]
    assert quotes["VWRL.L"].prev_close == 100.0  # only one bar: prev = last


def test_metadata_reads_the_chart_meta():
    meta = _provider(lambda r: httpx.Response(200, json=_chart("VWRL.L", [(date(2026, 9, 18), 1.0)]))).metadata("VWRL.L")
    assert (meta.name, meta.currency, meta.exchange, meta.quote_type) == (
        "Vanguard FTSE All-World UCITS ETF",
        "GBp",
        "LSE",
        "ETF",
    )


def test_history_is_limited_to_the_requested_days():
    bars = [(date(2026, 9, d), 100.0 + d) for d in range(14, 19)]
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_chart("VWRL.L", bars))

    history = _provider(handler).history(["VWRL.L"], date(2026, 9, 15), date(2026, 9, 17))

    assert [c.date for c in history["VWRL.L"]] == [date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17)]
    params = requests[0].url.params
    assert int(params["period2"]) - int(params["period1"]) == 3 * 86400  # end is exclusive


def test_search_maps_quotes_and_falls_back_to_an_exact_symbol():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            q = request.url.params["q"]
            quotes = [{"symbol": "VWRL.L", "shortname": "VANGUARD FTSE ALL-WORLD", "exchange": "LSE", "quoteType": "ETF"}]
            return httpx.Response(200, json={"quotes": quotes if q == "vanguard" else []})
        return httpx.Response(200, json=_chart("0P0000XXXX.L", [(date(2026, 9, 18), 1.0)], currency="GBP"))

    provider = _provider(handler)
    [hit] = provider.search("vanguard")
    assert (hit.symbol, hit.name, hit.exchange, hit.quote_type) == ("VWRL.L", "VANGUARD FTSE ALL-WORLD", "LSE", "ETF")

    [exact] = provider.search("0P0000XXXX.L")
    assert exact.symbol == "0P0000XXXX.L"
