from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.importers.canonical import (
    header_signature,
    parse_canonical_dataframe,
)


def test_header_signature_is_sorted_lowercased():
    assert header_signature(["Date", "TYPE", "amount_gbp"]) == "amount_gbp|date|type"


def test_parse_canonical_dataframe_reads_valid_rows():
    df = pd.DataFrame(
        [
            {
                "date": "2021-04-06",
                "type": "DEPOSIT",
                "symbol": "",
                "isin": "",
                "name": "",
                "units": "",
                "price": "",
                "currency": "GBP",
                "fx_gbp_per_unit": "1",
                "amount_gbp": "20000.00",
                "fees_gbp": "0",
                "contribution_source": "personal",
                "external_id": "ext-1",
                "notes": "Tax year subscription",
            }
        ]
    )
    rows, errors = parse_canonical_dataframe(df)
    assert errors == []
    assert len(rows) == 1
    row = rows[0]
    assert row.date == date(2021, 4, 6)
    assert row.type == "DEPOSIT"
    assert row.amount_gbp == 20000.00
    assert row.external_id == "ext-1"


def test_parse_canonical_dataframe_collects_row_errors_without_raising():
    df = pd.DataFrame(
        [
            {"date": "", "type": "DEPOSIT", "amount_gbp": "10"},  # missing date
            {"date": "2021-04-06", "type": "NOT_A_TYPE", "amount_gbp": "10"},  # bad type
            {"date": "2021-04-07", "type": "DEPOSIT", "amount_gbp": "10"},  # valid
        ]
    )
    rows, errors = parse_canonical_dataframe(df)
    assert len(rows) == 1
    assert len(errors) == 2
    # header is file row 1, so pandas index 0/1/2 map to file rows 2/3/4
    assert errors[0].row == 2
    assert errors[1].row == 3


def test_dedupe_hash_is_stable_and_sensitive_to_key_fields():
    df = pd.DataFrame(
        [{"date": "2021-04-07", "type": "BUY", "symbol": "VUSA.L", "units": "10", "amount_gbp": "-100"}]
    )
    rows, _ = parse_canonical_dataframe(df)
    h1 = rows[0].dedupe_hash()
    h2 = rows[0].dedupe_hash()
    assert h1 == h2

    df2 = pd.DataFrame(
        [{"date": "2021-04-07", "type": "BUY", "symbol": "VUSA.L", "units": "11", "amount_gbp": "-100"}]
    )
    rows2, _ = parse_canonical_dataframe(df2)
    assert rows2[0].dedupe_hash() != h1
