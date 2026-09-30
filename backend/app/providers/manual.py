"""Manual instruments never touch the network — price_service reads `manual_price_gbp` straight
off the instrument row. This provider exists only so `price_source = manual` still satisfies the
`PriceProvider` protocol wherever one is expected."""

from __future__ import annotations

from datetime import date

from app.providers.base import DailyClose, InstrumentMetadata, InstrumentSearchResult, Quote


class ManualProvider:
    def search(self, query: str) -> list[InstrumentSearchResult]:
        return []

    def metadata(self, symbol: str) -> InstrumentMetadata:
        return InstrumentMetadata(name=symbol, currency="GBP", exchange=None, quote_type=None)

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        return {}

    def history(self, symbols: list[str], start: date, end: date) -> dict[str, list[DailyClose]]:
        return {}
