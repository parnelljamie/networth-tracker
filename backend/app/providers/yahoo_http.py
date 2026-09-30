"""docs/07-mobile.md "Android shell": Yahoo prices over plain HTTPS, for the phone.

yfinance depends on curl_cffi, which has no Android build, so the phone calls Yahoo's public chart
and search endpoints directly. Same `PriceProvider` protocol and the same results as
`YahooProvider`: native prices and currency codes, with the latest daily bar standing in for the
live price during trading hours.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.providers.base import DailyClose, InstrumentMetadata, InstrumentSearchResult, Quote

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
# Yahoo refuses requests without a browser-like User-Agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) Waymark"}
TIMEOUT_S = 20.0


def _bar_date(timestamp: int, gmtoffset: int) -> date:
    """Daily bars are stamped at the exchange's open; shift to exchange time for the date."""
    return (datetime.fromtimestamp(timestamp, UTC) + timedelta(seconds=gmtoffset)).date()


def _closes(result: dict[str, Any]) -> list[DailyClose]:
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    offset = int((result.get("meta") or {}).get("gmtoffset") or 0)
    by_date: dict[date, float] = {}
    for ts, close in zip(timestamps, closes, strict=False):
        if close is None:
            continue
        by_date[_bar_date(int(ts), offset)] = float(close)  # a later bar for the same day wins
    return [DailyClose(date=d, close=c) for d, c in sorted(by_date.items())]


class YahooHttpProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.Client(headers=HEADERS, timeout=TIMEOUT_S, follow_redirects=True)
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        finally:
            if self._client is None:
                client.close()

    def _chart(self, symbol: str, params: dict[str, Any]) -> dict[str, Any] | None:
        data = self._get(CHART_URL.format(symbol=symbol), {"interval": "1d", **params})
        results = (data.get("chart") or {}).get("result") or []
        return results[0] if results else None

    def search(self, query: str) -> list[InstrumentSearchResult]:
        try:
            data = self._get(SEARCH_URL, {"q": query, "quotesCount": 10, "newsCount": 0})
        except Exception:
            logger.exception("Yahoo search failed for %r", query)
            data = {}
        results = [
            InstrumentSearchResult(
                symbol=q["symbol"],
                name=q.get("shortname") or q.get("longname") or q["symbol"],
                exchange=q.get("exchange") or q.get("exchDisp"),
                quote_type=q.get("quoteType"),
            )
            for q in data.get("quotes") or []
            if "symbol" in q
        ]
        if results:
            return results
        # Same fallback as YahooProvider: treat the query as an exact symbol.
        try:
            meta = self.metadata(query)
        except Exception:
            return []
        return [InstrumentSearchResult(symbol=query, name=meta.name, exchange=meta.exchange, quote_type=meta.quote_type)]

    def metadata(self, symbol: str) -> InstrumentMetadata:
        result = self._chart(symbol, {"range": "5d"})
        if result is None:
            raise LookupError(symbol)
        meta = result.get("meta") or {}
        if not meta.get("currency"):
            raise LookupError(symbol)
        return InstrumentMetadata(
            name=meta.get("longName") or meta.get("shortName") or symbol,
            currency=meta["currency"],
            exchange=meta.get("exchangeName") or meta.get("fullExchangeName"),
            quote_type=meta.get("instrumentType"),
        )

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        out: dict[str, Quote] = {}
        for symbol in symbols:
            try:
                result = self._chart(symbol, {"range": "5d"})
                closes = _closes(result) if result else []
                if not closes:
                    continue
                last = closes[-1].close
                prev_close = closes[-2].close if len(closes) > 1 else last
                out[symbol] = Quote(last=last, prev_close=prev_close, bar_date=closes[-1].date)
            except Exception:
                logger.exception("Yahoo quote failed for %s", symbol)
        return out

    def history(self, symbols: list[str], start: date, end: date) -> dict[str, list[DailyClose]]:
        out: dict[str, list[DailyClose]] = {}
        period1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
        end_next = end + timedelta(days=1)  # exclusive, like YahooProvider
        period2 = int(datetime(end_next.year, end_next.month, end_next.day, tzinfo=UTC).timestamp())
        for symbol in symbols:
            try:
                result = self._chart(symbol, {"period1": period1, "period2": period2})
                if result:
                    out[symbol] = [c for c in _closes(result) if start <= c.date <= end]
            except Exception:
                logger.exception("Yahoo history failed for %s", symbol)
        return out
