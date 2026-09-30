from __future__ import annotations

from datetime import date

from app.services.importers.bank import BankRow, compute_daily_balances


def test_running_balance_column_newest_first_keeps_last_row_per_day():
    """docs/06-imports-future.md "Bank CSV -> daily balances": many banks export newest first,
    so we sort by (date, original row index) and keep the last row's balance per date — this
    fixture has two rows for 2024-01-05, and the *second* one in the file (higher row_index)
    should win, not the first."""
    rows = [
        BankRow(row_number=2, row_index=0, date=date(2024, 1, 5), amount=-15.0, balance=1000.0),
        BankRow(row_number=3, row_index=1, date=date(2024, 1, 5), amount=-5.0, balance=995.0),
        BankRow(row_number=4, row_index=2, date=date(2024, 1, 3), amount=20.0, balance=1015.0),
        BankRow(row_number=5, row_index=3, date=date(2024, 1, 1), amount=None, balance=980.0),
    ]
    balances = compute_daily_balances(rows, anchor_balance_gbp=None, anchor_date=None)
    assert balances == {
        date(2024, 1, 5): 995.0,
        date(2024, 1, 3): 1015.0,
        date(2024, 1, 1): 980.0,
    }


def test_walkback_from_anchor_when_no_balance_column():
    rows = [
        BankRow(row_number=2, row_index=0, date=date(2024, 2, 5), amount=-30.0, balance=None),
        BankRow(row_number=3, row_index=1, date=date(2024, 2, 5), amount=-10.0, balance=None),
        BankRow(row_number=4, row_index=2, date=date(2024, 2, 3), amount=100.0, balance=None),
        BankRow(row_number=5, row_index=3, date=date(2024, 2, 1), amount=-5.0, balance=None),
    ]
    balances = compute_daily_balances(rows, anchor_balance_gbp=900.0, anchor_date=date(2024, 2, 5))
    assert balances == {
        date(2024, 2, 5): 900.0,
        date(2024, 2, 3): 940.0,  # 900 - (-40 on 2024-02-05)
        date(2024, 2, 1): 840.0,  # 940 - 100 on 2024-02-03
    }


def test_walkback_without_anchor_raises_domain_error():
    from app.core.errors import DomainError

    rows = [BankRow(row_number=2, row_index=0, date=date(2024, 2, 5), amount=-30.0, balance=None)]
    try:
        compute_daily_balances(rows, anchor_balance_gbp=None, anchor_date=None)
        raise AssertionError("expected DomainError")
    except DomainError:
        pass
