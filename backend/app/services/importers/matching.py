"""docs/06-imports-future.md step 4 "Instrument matching": for each distinct (symbol, isin, name)
in the parsed rows, resolve to an instrument via, in order: a saved alias for this profile, an
existing instrument by symbol or ISIN, or a provider search the user picks/creates from. Chosen
matches are saved back as aliases so the same profile never asks again.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.imports import InstrumentAlias
from app.models.instruments import Instrument
from app.providers.base import PriceProvider
from app.services.importers.canonical import CanonicalRow


@dataclass
class UnmatchedKey:
    key: str
    symbol: str | None
    isin: str | None
    name: str | None
    suggestions: list[dict]


def distinct_instrument_rows(rows: list[CanonicalRow]) -> dict[str, CanonicalRow]:
    out: dict[str, CanonicalRow] = {}
    for row in rows:
        key = row.instrument_key()
        if key is not None and key not in out:
            out[key] = row
    return out


def _alias_lookup(db: Session, profile_name: str | None, alias: str) -> int | None:
    query = select(InstrumentAlias.instrument_id).where(InstrumentAlias.alias == alias)
    query = query.where(InstrumentAlias.profile_name == profile_name) if profile_name else query.where(
        InstrumentAlias.profile_name.is_(None)
    )
    return db.scalars(query).first()


def match_instruments(
    db: Session,
    profile_name: str | None,
    rows: list[CanonicalRow],
    provider: PriceProvider | None = None,
) -> tuple[dict[str, int], list[UnmatchedKey]]:
    """Returns (key -> instrument_id, list of keys still needing user resolution)."""
    by_key = distinct_instrument_rows(rows)
    matched: dict[str, int] = {}
    unmatched: list[UnmatchedKey] = []

    for key, row in by_key.items():
        instrument_id: int | None = None
        if row.symbol:
            instrument_id = _alias_lookup(db, profile_name, row.symbol)
        if instrument_id is None and row.isin:
            instrument_id = _alias_lookup(db, profile_name, row.isin)

        if instrument_id is None and row.symbol:
            instrument_id = db.scalars(
                select(Instrument.id).where(Instrument.symbol == row.symbol)
            ).first()
        if instrument_id is None and row.isin:
            instrument_id = db.scalars(
                select(Instrument.id).where(Instrument.isin == row.isin)
            ).first()

        if instrument_id is not None:
            matched[key] = instrument_id
            continue

        suggestions: list[dict] = []
        if provider is not None:
            query = row.isin or row.name or row.symbol or ""
            if query:
                try:
                    suggestions = [
                        {"symbol": s.symbol, "name": s.name, "exchange": s.exchange}
                        for s in provider.search(query)
                    ]
                except Exception:  # noqa: BLE001 — a failed lookup just means no suggestions
                    suggestions = []
        unmatched.append(
            UnmatchedKey(key=key, symbol=row.symbol, isin=row.isin, name=row.name, suggestions=suggestions)
        )

    return matched, unmatched


def save_alias(db: Session, profile_name: str | None, alias: str, instrument_id: int) -> None:
    existing = db.scalars(
        select(InstrumentAlias).where(
            InstrumentAlias.alias == alias,
            InstrumentAlias.profile_name == profile_name if profile_name else InstrumentAlias.profile_name.is_(None),
        )
    ).first()
    if existing is not None:
        existing.instrument_id = instrument_id
        return
    db.add(InstrumentAlias(alias=alias, profile_name=profile_name, instrument_id=instrument_id))
