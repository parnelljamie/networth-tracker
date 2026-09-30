"""docs/06-imports-future.md "Bank CSV -> daily balances".

- If the file has a running balance column: for each date keep the balance of the last row that
  day, respecting file order (many banks export newest first, so we sort by date then original
  row index — same-date rows keep their file order, and the *last* one in that order wins).
- If not: the user supplies an anchor balance on the latest date and we walk backwards,
  `balance(d-1) = balance(d) - sum(amounts on d)`.

Raw bank transactions are never stored (net worth only, no budgeting) — only the resulting daily
`balance_entries`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.core.errors import DomainError
from app.services.importers.canonical import RowError, _to_date


@dataclass
class BankRow:
    row_number: int
    row_index: int  # 0-based original file order
    date: date
    amount: float | None
    balance: float | None


def parse_bank_dataframe(df: pd.DataFrame) -> tuple[list[BankRow], list[RowError]]:
    rows: list[BankRow] = []
    errors: list[RowError] = []
    has_balance_col = "balance" in df.columns
    has_amount_col = "amount" in df.columns
    for i, raw in df.iterrows():
        row_number = int(i) + 2
        try:
            d = _to_date(raw.get("date"))
            amount = _num(raw.get("amount")) if has_amount_col else None
            balance = _num(raw.get("balance")) if has_balance_col else None
            rows.append(BankRow(row_number=row_number, row_index=int(i), date=d, amount=amount, balance=balance))
        except Exception as exc:  # noqa: BLE001
            errors.append(RowError(row=row_number, message=str(exc)))
    return rows, errors


def _num(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text.replace(",", ""))


def has_running_balance_column(rows: list[BankRow]) -> bool:
    return any(r.balance is not None for r in rows)


def daily_balances_from_running_column(rows: list[BankRow]) -> dict[date, float]:
    """Sort by (date, original row index) ascending; within a date, the last row in that
    ascending-row-index order is the last row for that date in file order."""
    ordered = sorted((r for r in rows if r.balance is not None), key=lambda r: (r.date, r.row_index))
    result: dict[date, float] = {}
    for row in ordered:
        result[row.date] = row.balance  # later (higher row_index) same-date rows overwrite earlier
    return result


def daily_balances_from_walkback(
    rows: list[BankRow], anchor_balance_gbp: float, anchor_date: date
) -> dict[date, float]:
    sums: dict[date, float] = {}
    for row in rows:
        if row.amount is None:
            continue
        if row.date > anchor_date:
            continue  # anchor is the latest known date; later rows aren't handled here
        sums[row.date] = sums.get(row.date, 0.0) + row.amount

    distinct_dates = sorted({*sums.keys(), anchor_date}, reverse=True)
    if not distinct_dates:
        raise DomainError("validation", "No dated rows to walk back from", field=None)

    balances: dict[date, float] = {distinct_dates[0]: round(anchor_balance_gbp, 2)}
    for prev_d, cur_d in zip(distinct_dates[1:], distinct_dates[:-1], strict=True):
        balances[prev_d] = round(balances[cur_d] - sums.get(cur_d, 0.0), 2)
    return balances


def compute_daily_balances(
    rows: list[BankRow], anchor_balance_gbp: float | None, anchor_date: date | None
) -> dict[date, float]:
    if has_running_balance_column(rows):
        return daily_balances_from_running_column(rows)
    if anchor_balance_gbp is None or anchor_date is None:
        raise DomainError(
            "validation",
            "This file has no running balance column — enter the balance on its latest date "
            "so earlier balances can be walked back",
            field="anchor_balance_gbp",
        )
    return daily_balances_from_walkback(rows, anchor_balance_gbp, anchor_date)
