"""docs/03-domain-logic.md §3. Wrap every call in try/except, log, and return partial results.
Never call `.info` during refreshes — it is slow and rate-limited; only `metadata()` touches it,
wrapped in its own try, and only when an instrument is created."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import yfinance as yf

from app.providers.base import DailyClose, InstrumentMetadata, InstrumentSearchResult, Quote

logger = logging.getLogger("app.providers.yahoo")

_CHUNK_SIZE = 20


class YahooProvider:
    def search(self, query: str) -> list[InstrumentSearchResult]:
        try:
            results = yf.Search(query, max_results=10, news_count=0).quotes
            return [
                InstrumentSearchResult(
                    symbol=r["symbol"],
                    name=r.get("shortname") or r.get("longname") or r["symbol"],
                    exchange=r.get("exchange") or r.get("exchDisp"),
                    quote_type=r.get("quoteType"),
                )
                for r in results
                if "symbol" in r
            ]
        except Exception:
            logger.exception("Yahoo search failed for %r; falling back to exact-symbol lookup", query)
            try:
                meta = self.metadata(query)
                return [
                    InstrumentSearchResult(
                        symbol=query, name=meta.name, exchange=meta.exchange, quote_type=meta.quote_type
                    )
                ]
            except Exception:
                return []

    def metadata(self, symbol: str) -> InstrumentMetadata:
        t = yf.Ticker(symbol)
        fast = t.fast_info
        name = symbol
        try:
            info = t.info
            name = info.get("longName") or info.get("shortName") or symbol
        except Exception:
            logger.warning("Could not fetch slow .info for %s; using symbol as name", symbol)
        return InstrumentMetadata(
            name=name,
            currency=fast["currency"],
            exchange=fast.get("exchange"),
            quote_type=fast.get("quote_type") or fast.get("quoteType"),
        )

    def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        if not symbols:
            return {}
        out: dict[str, Quote] = {}
        try:
            df = yf.download(
                symbols,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=True,
                timeout=20,
            )
        except Exception:
            logger.exception("Yahoo quotes download failed for %s", symbols)
            return out

        for symbol in symbols:
            try:
                closes = _closes_for_symbol(df, symbol, symbols)
                if closes is None or closes.empty:
                    continue
                last = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) > 1 else last
                bar_date = closes.index[-1].date()
                out[symbol] = Quote(last=last, prev_close=prev_close, bar_date=bar_date)
            except Exception:
                logger.exception("Could not extract a quote for %s", symbol)
        return out

    def history(self, symbols: list[str], start: date, end: date) -> dict[str, list[DailyClose]]:
        out: dict[str, list[DailyClose]] = {}
        for i in range(0, len(symbols), _CHUNK_SIZE):
            chunk = symbols[i : i + _CHUNK_SIZE]
            try:
                df = yf.download(
                    chunk,
                    start=start,
                    end=end + timedelta(days=1),
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,
                    actions=False,
                    progress=False,
                    threads=True,
                    timeout=20,
                )
            except Exception:
                logger.exception("Yahoo history download failed for chunk %s", chunk)
                continue
            for symbol in chunk:
                try:
                    closes = _closes_for_symbol(df, symbol, chunk)
                    if closes is None:
                        continue
                    out[symbol] = [
                        DailyClose(date=idx.date(), close=float(v))
                        for idx, v in closes.dropna().items()
                    ]
                except Exception:
                    logger.exception("Could not extract history for %s", symbol)
        return out


def _closes_for_symbol(df, symbol: str, requested: list[str]):
    """`Close` series for one symbol from a (possibly flat, single-symbol) yf.download frame."""
    if df is None or df.empty:
        return None
    if isinstance(df.columns, type(df.columns)) and getattr(df.columns, "nlevels", 1) > 1:
        if symbol not in df.columns.get_level_values(0):
            return None
        return df[symbol]["Close"].dropna()
    # Flat frame: only happens when a single symbol was requested.
    if len(requested) == 1 and "Close" in df.columns:
        return df["Close"].dropna()
    return None
