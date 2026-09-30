from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc, now_utc_naive
from app.core.enums import PriceSource
from app.db import SessionLocal
from app.engine.prices import MissingFxRate, fix_pence_glitch, fx_symbol, major_currency, to_gbp
from app.models.accounts import Account
from app.models.instruments import Instrument
from app.models.positions import Position
from app.models.prices import FxRate, InstrumentPrice
from app.providers.base import InstrumentMetadata, InstrumentSearchResult, PriceProvider
from app.services import settings_service

logger = logging.getLogger("app.price_service")

FRESH_LIVE_WINDOW = timedelta(days=4)
STALE_AFTER_DAYS = 10


@dataclass
class PriceResult:
    price_gbp: float
    is_stale: bool
    warning: str | None


@dataclass
class RefreshResult:
    status: str  # ok | partial | already_running | recent
    refreshed: int
    failed: list[dict] = field(default_factory=list)
    at: datetime = field(default_factory=now_utc)


def latest_price_on_or_before(db: Session, instrument_id: int, on: date) -> InstrumentPrice | None:
    return db.scalars(
        select(InstrumentPrice)
        .where(InstrumentPrice.instrument_id == instrument_id, InstrumentPrice.date <= on)
        .order_by(InstrumentPrice.date.desc())
        .limit(1)
    ).first()


def _manual_price_gbp(db: Session, instrument: Instrument, on: date, live: bool = False) -> PriceResult:
    """docs/03-domain-logic.md §1 step 1: a manual instrument's price for `on`.

    `manual_price_gbp` is the single price the user typed, so on its own it values every historical
    date at today's figure. Imported history (e.g. a pension statement carrying a unit price per
    dealing date) lands in `instrument_prices`, so prefer whichever of the two was stated later
    on/before `on`, with the typed price winning a tie as the more deliberate figure.

    When the instrument follows a Yahoo instrument (`tracks_instrument_id`), that stated price is
    carried forward by the tracked instrument's move since its date, so the value moves daily
    between statements and snaps back to the real unit price at each new one.

    Never flagged stale: for a manual instrument the user *is* the price source, so a dated row
    must not mark every backfilled snapshot `is_estimated`. The one exception is having nothing
    dated on/before `on` at all, where the typed price is a fallback rather than an observation.
    """
    row = latest_price_on_or_before(db, instrument.id, on)
    typed, typed_date = instrument.manual_price_gbp, instrument.manual_price_date
    typed_usable = typed is not None and (typed_date is None or typed_date <= on)

    if typed_usable and row is not None:
        if typed_date is None or typed_date >= row.date:
            stated, stated_on = typed, typed_date
        else:
            stated, stated_on = row.close_gbp, row.date
    elif typed_usable:
        stated, stated_on = typed, typed_date
    elif row is not None:
        stated, stated_on = row.close_gbp, row.date
    elif typed is not None:
        return PriceResult(typed, True, None)  # typed price postdates `on`; better than zero
    else:
        return PriceResult(0.0, True, f"No manual price set for {instrument.symbol}")

    if stated_on is not None and stated_on < on:
        stated *= _tracked_move(db, instrument, stated_on, on, live)
    return PriceResult(stated, False, None)


def tracked_instrument(db: Session, instrument: Instrument) -> Instrument | None:
    """The Yahoo instrument a manual one follows, if any."""
    if instrument.price_source != PriceSource.manual or instrument.tracks_instrument_id is None:
        return None
    target = db.get(Instrument, instrument.tracks_instrument_id)
    if target is None or target.price_source != PriceSource.yahoo:
        return None
    return target


def _tracked_move(db: Session, instrument: Instrument, since: date, on: date, live: bool) -> float:
    """How far the tracked instrument moved from `since` to `on` (1.0 when not tracking, or when
    either end has no price)."""
    target = tracked_instrument(db, instrument)
    if target is None:
        return 1.0
    base = latest_price_on_or_before(db, target.id, since)
    now = price_gbp(db, target, on, live)
    if base is None or base.close_gbp <= 0 or now.price_gbp <= 0:
        return 1.0
    return now.price_gbp / base.close_gbp


def price_gbp(db: Session, instrument: Instrument, on: date, live: bool) -> PriceResult:
    """docs/03-domain-logic.md §1 "Price for a date"."""
    if instrument.price_source == PriceSource.manual:
        return _manual_price_gbp(db, instrument, on, live)

    if (
        live
        and instrument.last_price_at is not None
        and instrument.last_price_gbp is not None
        and now_utc_naive() - instrument.last_price_at <= FRESH_LIVE_WINDOW
    ):
        return PriceResult(instrument.last_price_gbp, False, None)

    row = latest_price_on_or_before(db, instrument.id, on)
    if row is None:
        return PriceResult(0.0, True, f"No price available for {instrument.symbol}")
    is_stale = (on - row.date).days > STALE_AFTER_DAYS
    return PriceResult(row.close_gbp, is_stale, None)


def day_change_contribution(instrument: Instrument, units: float, on: date, db: Session | None = None) -> float:
    """docs/03-domain-logic.md §1 "Day change": 0 for non-Yahoo or not-refreshed-today instruments.
    A manual instrument that tracks a Yahoo one (`db` given) moves by the tracked day change."""
    quoted = instrument
    if instrument.price_source == PriceSource.manual and db is not None:
        quoted = tracked_instrument(db, instrument) or instrument
    if quoted.price_source != PriceSource.yahoo:
        return 0.0
    if quoted.last_price_at is None or quoted.last_price_at.date() != on:
        return 0.0
    if not quoted.last_price_gbp or quoted.prev_close_gbp is None:
        return 0.0
    if quoted is instrument:
        return units * (instrument.last_price_gbp - instrument.prev_close_gbp)
    # Same fractional move, applied to the manual instrument's own (scaled) price.
    price_now = price_gbp(db, instrument, on, live=True).price_gbp
    return units * price_now * (1 - quoted.prev_close_gbp / quoted.last_price_gbp)


# ---------------------------------------------------------------------------
# Refresh (module-level, non-blocking lock; docs/03-domain-logic.md §3)
# ---------------------------------------------------------------------------

_refresh_lock = threading.Lock()
_backoff_until: datetime | None = None


def with_tracked_ids(db: Session, instrument_ids: list[int] | set[int]) -> set[int]:
    """`instrument_ids` plus the Yahoo instruments any of them follow."""
    ids = set(instrument_ids)
    if ids:
        ids |= set(
            db.scalars(
                select(Instrument.tracks_instrument_id).where(
                    Instrument.id.in_(ids), Instrument.tracks_instrument_id.isnot(None)
                )
            ).all()
        )
    return ids


def held_yahoo_instruments(db: Session) -> list[Instrument]:
    """Yahoo instruments to refresh: those held, and those a held manual instrument follows."""
    ids = with_tracked_ids(
        db,
        db.scalars(
            select(Position.instrument_id)
            .join(Account, Account.id == Position.account_id)
            .where(Account.is_archived.is_(False))
            .distinct()
        ).all(),
    )
    if not ids:
        return []
    return list(
        db.scalars(
            select(Instrument).where(
                Instrument.id.in_(ids), Instrument.price_source == PriceSource.yahoo
            )
        ).all()
    )


def _upsert_fx_rate(db: Session, currency: str, on: date, gbp_per_unit: float) -> None:
    row = db.get(FxRate, (currency, on))
    if row is None:
        db.add(FxRate(currency=currency, date=on, gbp_per_unit=gbp_per_unit))
    else:
        row.gbp_per_unit = gbp_per_unit


def _upsert_instrument_price(
    db: Session, instrument_id: int, on: date, close_native: float, close_gbp: float
) -> None:
    row = db.get(InstrumentPrice, (instrument_id, on))
    if row is None:
        db.add(
            InstrumentPrice(
                instrument_id=instrument_id,
                date=on,
                close_native=close_native,
                close_gbp=close_gbp,
                source=PriceSource.yahoo,
            )
        )
    else:
        row.close_native = close_native
        row.close_gbp = close_gbp
        row.source = PriceSource.yahoo


def refresh_quotes(db: Session, provider: PriceProvider, force: bool = False) -> RefreshResult:
    global _backoff_until

    if _backoff_until is not None and now_utc() < _backoff_until:
        return RefreshResult(status="recent", refreshed=0)

    if not _refresh_lock.acquire(blocking=False):
        return RefreshResult(status="already_running", refreshed=0)

    try:
        instruments = held_yahoo_instruments(db)
        if not instruments:
            return RefreshResult(status="ok", refreshed=0)

        refresh_minutes = settings_service.get(db, "price_refresh_minutes", 15)
        if not force and all(
            i.last_price_at is not None
            and now_utc_naive() - i.last_price_at < timedelta(minutes=refresh_minutes)
            for i in instruments
        ):
            return RefreshResult(status="recent", refreshed=0)

        currencies = {
            major_currency(i.quote_currency)[0]
            for i in instruments
            if major_currency(i.quote_currency)[0] != "GBP"
        }
        fx_symbols = {c: fx_symbol(c) for c in currencies}
        all_symbols = [i.symbol for i in instruments] + list(fx_symbols.values())

        quotes = provider.quotes(all_symbols)

        if not quotes:
            # Nothing came back at all for a non-empty request: likely throttled. Back off.
            _backoff_until = now_utc() + timedelta(minutes=15)
            for instrument in instruments:
                instrument.last_fetch_error = "no data"
            db.commit()
            return RefreshResult(
                status="partial",
                refreshed=0,
                failed=[{"symbol": i.symbol, "error": "no data"} for i in instruments],
            )
        _backoff_until = None

        fx_rates: dict[str, float] = {}
        for currency, symbol in fx_symbols.items():
            q = quotes.get(symbol)
            if q is not None:
                fx_rates[currency] = q.last
                _upsert_fx_rate(db, currency, q.bar_date, q.last)

        refreshed = 0
        failed: list[dict] = []
        for instrument in instruments:
            q = quotes.get(instrument.symbol)
            if q is None:
                instrument.last_fetch_error = "no data"
                failed.append({"symbol": instrument.symbol, "error": "no data"})
                continue
            try:
                price_native_gbp = to_gbp(q.last, instrument.quote_currency, fx_rates)
                prev_native_gbp = to_gbp(q.prev_close, instrument.quote_currency, fx_rates)
            except MissingFxRate:
                error = f"missing FX rate for {major_currency(instrument.quote_currency)[0]}"
                instrument.last_fetch_error = error
                failed.append({"symbol": instrument.symbol, "error": error})
                continue

            price_native_gbp, _ = fix_pence_glitch(
                price_native_gbp, instrument.last_price_gbp or prev_native_gbp
            )

            instrument.last_price_native = q.last
            instrument.last_price_gbp = round(price_native_gbp, 6)
            instrument.prev_close_gbp = round(prev_native_gbp, 6)
            instrument.last_price_at = now_utc_naive()
            instrument.last_fetch_error = None
            _upsert_instrument_price(db, instrument.id, q.bar_date, q.last, price_native_gbp)
            refreshed += 1

        db.commit()
        return RefreshResult(
            status="ok" if not failed else "partial", refreshed=refreshed, failed=failed
        )
    finally:
        _refresh_lock.release()


# ---------------------------------------------------------------------------
# History backfill
# ---------------------------------------------------------------------------


def _trading_days_missing(existing: set[date], start: date, end: date) -> bool:
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in existing:
            return True
        d += timedelta(days=1)
    return False


def ensure_history(
    db: Session, provider: PriceProvider, instrument_ids: list[int], start: date, end: date
) -> None:
    """Fill missing trading-day history for the given instruments (and any Yahoo instruments they
    follow) between start and end."""
    ids = with_tracked_ids(db, instrument_ids)
    instruments = list(db.scalars(select(Instrument).where(Instrument.id.in_(ids))).all())
    yahoo_instruments = [i for i in instruments if i.price_source == PriceSource.yahoo]
    if not yahoo_instruments:
        return

    to_fetch: list[Instrument] = []
    for instrument in yahoo_instruments:
        existing = set(
            db.scalars(
                select(InstrumentPrice.date).where(
                    InstrumentPrice.instrument_id == instrument.id,
                    InstrumentPrice.date >= start,
                    InstrumentPrice.date <= end,
                )
            ).all()
        )
        if _trading_days_missing(existing, start, end):
            to_fetch.append(instrument)
    if not to_fetch:
        return

    currencies = {
        major_currency(i.quote_currency)[0] for i in to_fetch if major_currency(i.quote_currency)[0] != "GBP"
    }
    fx_symbols = {c: fx_symbol(c) for c in currencies}
    symbols = [i.symbol for i in to_fetch] + list(fx_symbols.values())

    history = provider.history(symbols, start, end)

    fx_history: dict[str, dict[date, float]] = {
        currency: {row.date: row.close for row in history.get(symbol, [])}
        for currency, symbol in fx_symbols.items()
    }

    def fx_on(currency: str, on: date) -> float | None:
        for back in range(6):
            rate = fx_history.get(currency, {}).get(on - timedelta(days=back))
            if rate is not None:
                return rate
        return None

    for instrument in to_fetch:
        rows = history.get(instrument.symbol, [])
        currency = major_currency(instrument.quote_currency)[0]
        for row in rows:
            try:
                if currency == "GBP":
                    close_gbp = to_gbp(row.close, instrument.quote_currency, {})
                else:
                    rate = fx_on(currency, row.date)
                    if rate is None:
                        continue
                    close_gbp = to_gbp(row.close, instrument.quote_currency, {currency: rate})
            except MissingFxRate:
                continue
            _upsert_instrument_price(db, instrument.id, row.date, row.close, close_gbp)
    db.commit()


def backfill_new_instrument_history(instrument_id: int, provider: PriceProvider) -> None:
    """Runs in a background thread after instrument creation: 5 years of history."""
    try:
        with SessionLocal() as db:
            end = now_utc().date()
            start = end - timedelta(days=365 * 5)
            ensure_history(db, provider, [instrument_id], start, end)
    except Exception:
        logger.exception("Background history backfill failed for instrument %s", instrument_id)


def start_background_history_fetch(instrument_id: int, provider: PriceProvider) -> None:
    thread = threading.Thread(
        target=backfill_new_instrument_history, args=(instrument_id, provider), daemon=True
    )
    thread.start()


# ---------------------------------------------------------------------------
# Search (in-memory cache, 10 min per docs/04-api.md)
# ---------------------------------------------------------------------------

_search_cache: dict[str, tuple[float, list[InstrumentSearchResult]]] = {}
_SEARCH_TTL_SECONDS = 600


def search(provider: PriceProvider, query: str) -> list[InstrumentSearchResult]:
    now = time.monotonic()
    cached = _search_cache.get(query)
    if cached is not None and now - cached[0] < _SEARCH_TTL_SECONDS:
        return cached[1]
    results = provider.search(query)
    _search_cache[query] = (now, results)
    return results


def fetch_metadata(provider: PriceProvider, symbol: str) -> InstrumentMetadata:
    return provider.metadata(symbol)
