# 06 · Historical imports (Phase 8)

The schema already supports this; nothing earlier needs redesign. Goal: turn exported history into
transactions and balance entries, then rebuild positions and daily snapshots back to the first date.

## What to gather

| Source | Export | Becomes |
|---|---|---|
| Each ISA / GIA / SIPP platform | full transaction history CSV (buys, sells, dividends, deposits, fees, transfers) | `transactions` |
| Banks | statement CSV per account | daily closing `balance_entries` |
| Workplace pensions | annual statements or contribution history | `balance_entries` (+ `transactions` if unit-level data exists) |
| Mortgage | completion statement, annual statements, product switch letters | `loan_details`, `loan_rate_periods`, statement `balance_entries`, `loan_overpayments` |
| Property | purchase price/date, any valuations | `balance_entries` (source `valuation`) |

Messy exports can first be converted to the canonical CSV below (by hand, in a spreadsheet or with a
script); the importer always accepts the canonical format.

## Canonical transaction CSV

```
date,type,symbol,isin,name,units,price,currency,fx_gbp_per_unit,amount_gbp,fees_gbp,contribution_source,external_id,notes
2021-04-06,DEPOSIT,,,,,,GBP,1,20000.00,0,personal,,Tax year subscription
2021-04-07,BUY,VUSA.L,IE00B3XXRP09,Vanguard S&P 500 UCITS ETF,300,6512,GBp,1,-19536.00,0,,,
2021-06-30,DIVIDEND,VUSA.L,,,,,GBP,1,41.22,0,,,
```
Signs follow `03-domain-logic.md` §2 (`amount_gbp` is the signed cash effect).

## Tables (Phase 8 migration)

`import_batches`, `import_profiles`, `instrument_aliases` as listed in `02-data-model.md`.
`transactions.import_batch_id` and `transactions.external_id` already exist.

## Pipeline (`services/importers/`)

1. **Upload** `POST /api/imports` (multipart: file, kind, account_id) → store the file under
   `data/imports/<batch_id>/`, create a `pending` batch, return detected headers + first 20 rows.
2. **Profile**: match `header_signature` (sorted, lower-cased header names joined by `|`) against
   `import_profiles`; otherwise the user maps columns in the UI and saves a profile. A mapping is JSON:
   `{"date": {"column": "Time", "format": "%Y-%m-%d %H:%M:%S"}, "type": {"column": "Action", "values": {"Market buy": "BUY", "Deposit": "DEPOSIT"}}, "units": {"column": "No. of shares"}, "price": {"column": "Price / share"}, "currency": {"column": "Currency (Price / share)"}, "amount_gbp": {"column": "Total", "sign_from_type": true}, "symbol": {"column": "Ticker"}, "isin": {"column": "ISIN"}, "external_id": {"column": "ID"}}`.
   Build profiles from the user's real exports; do not guess broker formats.
3. **Parse** with pandas into canonical rows. Row errors are collected (row number + message), not raised.
4. **Instrument matching**: for each distinct (symbol, isin, name): `instrument_aliases` → existing
   instrument by symbol or ISIN → `provider.search(isin or name)` suggestions → user picks or creates a
   manual instrument. Save choices as aliases for the profile.
5. **Dedupe**: `external_id` from the file, else `sha1(date|type|symbol|units|amount_gbp)`; skip rows
   whose `(account_id, external_id)` already exists.
6. **Dry run** `POST /api/imports/{id}/preview` → replay the account's *existing non-stand-in*
   transactions plus the parsed rows with `strict=False` and return:
   - counts by type, date range, row errors, ledger warnings (oversells usually mean missing history);
   - **reconciliation**: per instrument `current units/avg cost` (today's positions) vs
     `imported units/avg cost`, difference, and cash difference.
7. **Commit** `POST /api/imports/{id}/commit {replace_stand_ins: true, align_to_current: false}`:
   - in one DB transaction: when `replace_stand_ins`, delete the account's `OPENING_BALANCE` and
     `ADJUSTMENT` rows (source `opening`/`manual`) for instruments present in the import, and the cash
     stand-ins if the import includes cash flows;
   - insert parsed transactions with `source = import`, `import_batch_id`;
   - if `align_to_current`, add one `ADJUSTMENT` per instrument dated today so positions equal what
     the user had before (covers partial exports);
   - `rebuild_positions`, mark batch `committed`.
8. **Rebuild history** (background job with progress): `ensure_history` for every instrument from the
   earliest imported date, FX history likewise, then `snapshot_service.rebuild(account_id, earliest_date)`
   using `replay_series`.
9. **Undo** `POST /api/imports/{id}/rollback`: delete the batch's transactions, restore deleted
   stand-ins (keep them as JSON on the batch row before deleting), rebuild positions and snapshots.

## Bank CSV → daily balances

- If the file has a running balance column: for each date keep the balance of the last row that day
  (respect file order; many banks export newest first, so sort by date then original row index).
- If not: the user enters the balance on the latest date (anchor); walk backwards
  `balance(d−1) = balance(d) − Σ amounts on d`.
- Write one `balance_entries` row per date that had transactions (source `csv`) plus the anchor,
  then rebuild snapshots from the first date. Valuation carries balances forward between entries.
- Raw bank transactions are **not** stored (net worth only, no budgeting).

## Pensions, mortgage, property history

- Pension statements: one `balance_entries` row per statement date. Contribution history, if
  available, as DEPOSIT transactions only for holdings-method pensions.
- Mortgage: enter `loan_details` and every historical rate period, then statement balances. Optional
  "estimate monthly history": run `build_schedule` from the completion balance with historical rate
  periods and actual overpayments, and write month-end `balance_entries` with source `estimate`
  between real statements (never overwrite a real statement).
- Property: purchase price at purchase date plus valuations; growth model fills between them.
  Future option: index to the UK House Price Index for the region.

## UI

Import page = wizard (see `05-ui.md`) + history table of batches (file, account, rows imported,
skipped, date, status, Undo). The reconciliation step is the important screen: a table of
instruments with current vs imported units and avg cost, differences highlighted with icon + text,
and the two commit options explained in plain words.

## Tests

Fixture CSVs with fake data in `backend/tests/fixtures/imports/`; golden expected positions per
fixture; tests for dedupe, stand-in replacement, rollback, newest-first ordering and the bank
walk-back algorithm.

## Trading 212 API sync

`services/trading212_service.py` pulls a linked account's history from the Trading 212 Public API
(`/equity/history/orders`, `/dividends`, `/transactions`) and writes it as a canonical CSV batch
with `profile_name = "Trading 212 API"`, so everything above (dedupe, matching, preview,
commit, rollback, rebuild) applies unchanged.

- **Mapping**: filled orders → BUY/SELL (`amount_gbp` = ∓ `walletImpact.netValue`, units from the
  fill); `FOP` fills (shares transferred in/out, e.g. an ISA transfer) → non-cash
  `TRANSFER_IN`/`TRANSFER_OUT` with the reported value as cost basis; other non-TRADE fills (splits,
  stock distributions…) → non-cash instrument `ADJUSTMENT`. Both always stop for review; dividends → DIVIDEND (negative → TAX); DEPOSIT/WITHDRAW/FEE → same;
  TRANSFER → TRANSFER_IN/OUT (cash, `contribution_source = transfer`); interest → INTEREST.
  `external_id` is `t212:fill:<id>`, `t212:div:<reference>`, `t212:txn:<reference>`.
- **Earlier CSV imports**: `T212-EOF<fill id>` / `T212-<reference>` ids from a Trading 212 CSV
  import count as already synced; anything else already in the account (not a stand-in) with the
  same date, units and cash is skipped too (the CSV and API use different dividend references).
- **Instruments**: saved alias for the T212 ticker → instrument with the same ISIN → guessed Yahoo
  symbol (`VUSAl_EQ` → `VUSA.L`, `AAPL_US_EQ` → `AAPL`) → create it from Yahoo → first Yahoo
  search hit for the ISIN. Matches are saved as aliases and backfill `instruments.isin`. Anything
  left unmatched is picked in the changes popup (`POST /imports/{id}/instruments`).
- **Accept vs auto-commit**: a sync that changes holdings waits to be accepted: the first sync,
  any BUY/SELL, an unmatched instrument, a corporate action, or new ledger warnings. The app pops
  the changes up over whatever page is open (holdings before/after, cash, the transactions) with
  Accept / Not now; accepting commits with `replace_stand_ins = true`. Syncs that only move cash
  (deposits, dividends, interest, fees) commit by themselves (`replace_stand_ins = false`).
  Waiting syncs don't appear on the Import page; committed ones do, with Undo.
- **Paging**: history endpoints allow 6 requests/min; the client honours `x-ratelimit-*` headers
  and retries 429s. Incremental syncs stop once a whole newest-first page is already known.
- **Schedule**: daily at 06:30 and at startup (PC only) for links with `auto_sync`; every link
  also syncs from Settings → Trading 212 and whenever Update prices is pressed.
- **Regular Payments**: the API exposes no scheduled deposits or AutoInvest plans, so plans keep
  driving projections, but a linked account never records them (`auto_record` forced off,
  `record_due` skips it); linking deletes any pending recurring transactions already written.
