"""docs/06-imports-future.md "Canonical transaction CSV" + "Dedupe".

Parsing never raises on a bad row — row errors are collected (row number + message) so one typo
doesn't sink the whole file (docs/06-imports-future.md pipeline step 3).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from app.core.enums import TxnType

CANONICAL_TXN_COLUMNS = [
    "date",
    "type",
    "symbol",
    "isin",
    "name",
    "units",
    "price",
    "currency",
    "fx_gbp_per_unit",
    "amount_gbp",
    "fees_gbp",
    "contribution_source",
    "external_id",
    "notes",
]

CANONICAL_BALANCE_COLUMNS = ["date", "amount", "balance", "description"]

# ADJUSTMENT is instrument-bound when the row names one (e.g. a broker's split or stock
# distribution); without a symbol/ISIN/name it stays a cash adjustment, as before.
_INSTRUMENT_TYPES = {
    "BUY", "SELL", "DIVIDEND", "OPENING_BALANCE", "TRANSFER_IN", "TRANSFER_OUT", "SPLIT", "ADJUSTMENT",
}


@dataclass
class RowError:
    row: int
    message: str


@dataclass
class CanonicalRow:
    row_number: int
    date: date
    type: str
    symbol: str | None
    isin: str | None
    name: str | None
    units: float
    price: float | None
    currency: str
    fx_gbp_per_unit: float
    amount_gbp: float
    fees_gbp: float
    contribution_source: str | None
    external_id: str | None
    notes: str | None

    def instrument_key(self) -> str | None:
        if self.type not in _INSTRUMENT_TYPES:
            return None
        if not self.symbol and not self.isin and not self.name:
            return None
        return "|".join([self.symbol or "", self.isin or "", self.name or ""])

    def dedupe_hash(self) -> str:
        basis = f"{self.date.isoformat()}|{self.type}|{self.symbol or ''}|{self.units:g}|{self.amount_gbp:.2f}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def header_signature(headers: list[str]) -> str:
    """docs/06-imports-future.md: "sorted, lower-cased header names joined by |"."""
    return "|".join(sorted(h.strip().lower() for h in headers))


def _clean(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: object, default: float = 0.0) -> float:
    text = _clean(value)
    if text is None:
        return default
    return float(str(text).replace(",", ""))


def _to_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = _clean(value)
    if text is None:
        raise ValueError("date is required")
    if isinstance(value, pd.Timestamp):
        return value.date()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"unrecognised date {text!r}")
    return parsed.date()


def parse_canonical_dataframe(df: pd.DataFrame) -> tuple[list[CanonicalRow], list[RowError]]:
    rows: list[CanonicalRow] = []
    errors: list[RowError] = []
    for i, raw in df.iterrows():
        row_number = int(i) + 2  # header is file row 1, pandas index is 0-based
        try:
            d = _to_date(raw.get("date"))
            txn_type = (_clean(raw.get("type")) or "").upper()
            if not txn_type:
                raise ValueError("type is required")
            if txn_type not in TxnType.__members__:
                raise ValueError(f"unknown transaction type {txn_type!r}")
            rows.append(
                CanonicalRow(
                    row_number=row_number,
                    date=d,
                    type=txn_type,
                    symbol=_clean(raw.get("symbol")),
                    isin=_clean(raw.get("isin")),
                    name=_clean(raw.get("name")),
                    units=_to_float(raw.get("units")),
                    price=_to_float(raw.get("price"), default=None) if _clean(raw.get("price")) else None,
                    currency=_clean(raw.get("currency")) or "GBP",
                    fx_gbp_per_unit=_to_float(raw.get("fx_gbp_per_unit"), default=1.0) or 1.0,
                    amount_gbp=_to_float(raw.get("amount_gbp")),
                    fees_gbp=_to_float(raw.get("fees_gbp")),
                    contribution_source=_clean(raw.get("contribution_source")),
                    external_id=_clean(raw.get("external_id")),
                    notes=_clean(raw.get("notes")),
                )
            )
        except Exception as exc:  # noqa: BLE001 — collected, not raised, per spec
            errors.append(RowError(row=row_number, message=str(exc)))
    return rows, errors
