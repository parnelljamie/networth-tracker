"""A scriptable PriceProvider for tests. No test may touch the network."""

from __future__ import annotations

from datetime import date

from app.providers.base import DailyClose, InstrumentMetadata, InstrumentSearchResult, Quote


class FakeProvider:
    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._metadata: dict[str, InstrumentMetadata] = {}
        self._history: dict[str, list[DailyClose]] = {}
        self._search_results: list[InstrumentSearchResult] = []
        self.quote_calls: list[list[str]] = []

    def set_quote(self, symbol: str, last: float, prev_close: float, bar_date: date) -> None:
        self._quotes[symbol] = Quote(last=last, prev_close=prev_close, bar_date=bar_date)

    def set_metadata(self, symbol: str, meta: InstrumentMetadata) -> None:
        self._metadata[symbol] = meta

    def set_history(self, symbol: str, closes: list[DailyClose]) -> None:
        self._history[symbol] = closes

    def set_search_results(self, results: list[InstrumentSearchResult]) -> None:
        self._search_results = results

    def search(self, query: str) -> list[InstrumentSearchResult]:
        return self._search_results

    def metadata(self, symbol: str) -> InstrumentMetadata:
        if symbol not in self._metadata:
            raise LookupError(symbol)
        return self._metadata[symbol]

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        self.quote_calls.append(list(symbols))
        return {s: self._quotes[s] for s in symbols if s in self._quotes}

    def history(self, symbols: list[str], start: date, end: date) -> dict[str, list[DailyClose]]:
        return {s: self._history[s] for s in symbols if s in self._history}
