"""Applies an `import_profiles.mapping_json` column mapping to a raw DataFrame, producing a
canonical-shaped DataFrame. docs/06-imports-future.md step 2 "Profile" gives the mapping shape:

    {"date": {"column": "Time", "format": "%Y-%m-%d %H:%M:%S"},
     "type": {"column": "Action", "values": {"Market buy": "BUY", "Deposit": "DEPOSIT"}},
     "units": {"column": "No. of shares"},
     "amount_gbp": {"column": "Total", "sign_from_type": true}, ...}

A file whose headers already match the canonical column names needs no mapping at all — the
canonical DataFrame is used as-is (this is what the fixture CSVs in tests/fixtures/imports use).
"""

from __future__ import annotations

import pandas as pd

from app.services.importers.canonical import CANONICAL_BALANCE_COLUMNS, CANONICAL_TXN_COLUMNS

# Types whose cash effect on the account is negative (money leaves): used by `sign_from_type`
# when the source file gives an unsigned amount and a separate action/type column.
_NEGATIVE_TYPES = {"BUY", "WITHDRAWAL", "FEE", "TAX", "TRANSFER_OUT"}


def apply_mapping(df: pd.DataFrame, mapping: dict[str, dict], canonical_columns: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    type_series: pd.Series | None = None

    for field, spec in mapping.items():
        column = spec.get("column")
        if not column or column not in df.columns:
            continue
        series = df[column]

        if field == "date" and spec.get("format"):
            series = pd.to_datetime(series, format=spec["format"], errors="coerce")

        values_map = spec.get("values")
        if values_map:
            series = series.map(lambda v, m=values_map: m.get(str(v).strip(), v))

        out[field] = series
        if field == "type":
            type_series = out[field]

    for field, spec in mapping.items():
        if field != "amount_gbp" or not spec.get("sign_from_type"):
            continue
        if type_series is None or field not in out.columns:
            continue
        magnitude = out[field].abs()
        sign = type_series.map(lambda t: -1.0 if str(t).upper() in _NEGATIVE_TYPES else 1.0)
        out[field] = magnitude * sign

    for col in canonical_columns:
        if col not in out.columns:
            out[col] = None
    return out[canonical_columns]


def is_already_canonical(headers: list[str], canonical_columns: list[str]) -> bool:
    lowered = {h.strip().lower() for h in headers}
    required = {"date", "type"} if "type" in canonical_columns else {"date"}
    return required.issubset(lowered) and set(canonical_columns).issuperset(
        {h for h in lowered if h in canonical_columns}
    )


CANONICAL_COLUMNS_BY_KIND = {
    "transactions": CANONICAL_TXN_COLUMNS,
    "balances": CANONICAL_BALANCE_COLUMNS,
}
