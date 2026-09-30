"""docs/01-architecture.md "Price provider boundary". Everything above the provider works in GBP;
the provider returns native prices and currency codes only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class InstrumentSearchResult:
    symbol: str
    name: str
    exchange: str | None
    quote_type: str | None


@dataclass
class InstrumentMetadata:
    name: str
    currency: str
    exchange: str | None
    quote_type: str | None


@dataclass
class Quote:
    last: float
    prev_close: float
    bar_date: date


@dataclass
class DailyClose:
    date: date
    close: float


class PriceProvider(Protocol):
    def search(self, query: str) -> list[InstrumentSearchResult]: ...
    def metadata(self, symbol: str) -> InstrumentMetadata: ...
    def quotes(self, symbols: list[str]) -> dict[str, Quote]: ...
    def history(self, symbols: list[str], start: date, end: date) -> dict[str, list[DailyClose]]: ...
