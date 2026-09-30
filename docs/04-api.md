# 04 · API contract

Base path `/api`. JSON, `snake_case`. Dates `YYYY-MM-DD`, timestamps UTC ISO-8601, money GBP
floats, rates as fractions. `person_id` query param scopes a read to one person's share; omitted
means household (people with `include_in_household = true`).

Errors: `422 {"error": {"code": "validation", "message": "...", "field": "owners"}}`,
`404 {"error": {"code": "not_found", ...}}`, `409 {"error": {"code": "conflict", ...}}`.

Pydantic schemas live in `app/schemas/<area>.py`; names below are the schema class names.

## Health
| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{status, version, db_ok, scheduler_running, last_price_refresh_at}` |

## People
| Method | Path | Body / notes |
|---|---|---|
| GET | `/people?include_archived=false` | `Person[]` |
| POST | `/people` | `PersonCreate {name, color, date_of_birth?, retirement_age?, include_in_household?}` |
| PATCH | `/people/{id}` | partial `PersonCreate`, `is_archived?` |
| DELETE | `/people/{id}` | 409 if the person owns any account (archive instead) |

## Accounts
| Method | Path | Body / notes |
|---|---|---|
| GET | `/accounts?person_id&category&include_archived=false` | `AccountSummary[]` (includes current valuation) |
| POST | `/accounts` | `AccountCreate` (below) |
| GET | `/accounts/{id}` | `AccountDetail` = summary + `owners`, `growth_model?`, `property?`, `loan?` |
| PATCH | `/accounts/{id}` | partial; owners replace wholesale |
| POST | `/accounts/{id}/archive` · `/unarchive` | |
| DELETE | `/accounts/{id}` | 409 if it has snapshots, transactions or balance entries |
| GET | `/accounts/{id}/history?from&to` | `[{date, value_gbp, cost_basis_gbp, net_contributions_gbp, is_estimated}]` |

`AccountCreate`:
```json
{
  "name": "Trading 212 S&S ISA", "category": "investment", "wrapper": "isa",
  "valuation_method": "holdings", "provider": "Trading 212",
  "owners": [{"person_id": 1, "share": 1.0}],
  "include_in_networth": true, "is_liquid": null,
  "expected_return_rate": null, "annual_fee_rate": 0.0015, "interest_rate": null,
  "opened_date": "2021-04-06", "notes": null,
  "initial_balance": {"date": "2026-09-15", "balance_gbp": 1250.00, "source": "manual"},
  "growth_model": {"annual_rate": -0.15, "method": "compound", "floor_value_gbp": 1500, "cap_value_gbp": null},
  "property": {"address": "…", "purchase_date": "2019-06-01", "purchase_price_gbp": 325000, "is_main_residence": true},
  "loan": {"secured_on_account_id": 12, "lender": "Nationwide", "original_amount_gbp": 260000,
           "start_date": "2019-06-01", "maturity_date": "2049-06-01", "repayment_type": "repayment",
           "payment_day": 1, "overpayment_effect": "reduce_term", "overpayment_allowance_rate": 0.10,
           "fallback_rate": 0.0699,
           "rate_periods": [{"start_date": "2024-06-01", "end_date": "2029-05-31", "annual_rate": 0.0419,
                             "rate_type": "fixed", "label": "5yr fix", "payment_override_gbp": null}]}
}
```
Only the sub-objects relevant to the category are accepted; `is_liquid: null` means category default.

`AccountSummary`:
```json
{
  "id": 3, "name": "Trading 212 S&S ISA", "category": "investment", "wrapper": "isa",
  "valuation_method": "holdings", "provider": "Trading 212",
  "owners": [{"person_id": 1, "name": "James", "color": "#2a78d6", "share": 1.0}],
  "value_gbp": 48210.55, "scoped_value_gbp": 48210.55,
  "cost_basis_gbp": 41000.00, "gain_gbp": 7210.55, "gain_pct": 0.1759,
  "day_change_gbp": 212.40, "day_change_pct": 0.0044,
  "is_liability": false, "is_liquid": true, "include_in_networth": true,
  "is_estimated": false, "last_updated": "2026-09-15T13:45:00Z",
  "staleness": "ok"
}
```
`staleness`: `ok | warn | alert` from `settings.stale_balance_days` (balance/model/amortising
accounts: age of latest entry) or price age (holdings: `warn` if any held price is >3 days old).

## Balances (balance, model and amortising accounts)
| Method | Path | Body / notes |
|---|---|---|
| GET | `/accounts/{id}/balances` | `BalanceEntry[]` newest first |
| POST | `/accounts/{id}/balances` | `{date, balance_gbp, source?, notes?}` upserts on date; triggers snapshot rebuild from that date |
| PATCH / DELETE | `/balances/{entry_id}` | rebuild from the earlier of old/new date |
| GET | `/balances/quick-update?person_id` | `[{account_id, name, category, owners, valuation_method, last_date, last_balance_gbp, modelled_value_gbp, days_since, staleness}]` |
| POST | `/balances/bulk` | `{entries: [{account_id, date, balance_gbp, source?}]}` → `{saved}` |

## Growth models, property, loans
| Method | Path | Body / notes |
|---|---|---|
| PUT | `/accounts/{id}/growth-model` | `{annual_rate, method, floor_value_gbp?, cap_value_gbp?}` |
| PUT | `/accounts/{id}/property` | property details |
| PUT | `/accounts/{id}/loan` | loan details (without rate periods) |
| GET, POST | `/accounts/{id}/rate-periods` | `RatePeriod` rows; POST rejects overlaps (422) |
| PATCH, DELETE | `/rate-periods/{id}` | |
| GET, POST | `/accounts/{id}/overpayments` | `{date, amount_gbp, is_planned, notes?}` |
| PATCH, DELETE | `/overpayments/{id}` | |
| GET | `/accounts/{id}/schedule?include_planned=true` | `LoanSchedule` (below) |
| POST | `/accounts/{id}/schedule/simulate` | `{extra_monthly_gbp, lump_sums: [{date, amount_gbp}], overpayment_effect?}` → `LoanSimulation`, nothing saved |
| GET | `/accounts/{id}/equity` | property only: `{value_gbp, loans: [{account_id, name, owed_gbp}], equity_gbp, ltv, by_person: [{person_id, equity_gbp}]}` |

`LoanSchedule`:
```json
{
  "summary": {
    "anchor": {"date": "2026-08-01", "balance_gbp": 214530.12, "source": "statement"},
    "estimated_balance_today_gbp": 214102.77,
    "current_rate": 0.0419, "current_period": {"label": "5yr fix", "end_date": "2029-05-31", "days_left": 988},
    "monthly_payment_gbp": 1398.20, "payoff_date": "2049-06-01", "months_remaining": 273,
    "total_interest_remaining_gbp": 131204.55,
    "baseline": {"payoff_date": "2049-06-01", "total_interest_remaining_gbp": 131204.55}
  },
  "rows": [{"date": "2026-10-01", "annual_rate": 0.0419, "opening_balance": 214102.77, "payment": 1398.20,
            "interest": 747.51, "principal": 650.69, "overpayment": 0.0, "closing_balance": 213452.08}],
  "allowance_warnings": [{"period_label": "5yr fix", "year_start": "2027-06-01", "allowed_gbp": 21000.0, "planned_gbp": 24000.0}]
}
```
`LoanSimulation`: `{payoff_date, months_saved, interest_saved_gbp, first_changed_payment_gbp, chart: [{date, baseline_balance_gbp, simulated_balance_gbp}]}`.

## Instruments and prices
| Method | Path | Body / notes |
|---|---|---|
| GET | `/instruments/search?q=` | network; `[{symbol, name, exchange, quote_type}]`; in-memory cache 10 min |
| POST | `/instruments` | `{symbol, price_source, asset_class?, name?, manual_price_gbp?}`; yahoo: fetches metadata synchronously (timeout 10 s) then 5-year history in background. Existing symbol returns the existing row (200) |
| GET | `/instruments` · `/instruments/{id}` | |
| PATCH | `/instruments/{id}` | `{name?, asset_class?, isin?, manual_price_gbp?, manual_price_date?, tracks_instrument_id?}` (tracking: manual instrument following a Yahoo one, 422 otherwise; price changes rebuild holders' snapshots) |
| GET | `/instruments/{id}/prices?from&to` | `[{date, close_gbp}]` |
| POST | `/prices/refresh` | `{force: false}` → `{status: ok|partial|already_running|recent, refreshed, failed: [{symbol, error}], at}` |
| GET | `/prices/status` | `{last_refresh_at, next_refresh_at, market_open, stale: [{instrument_id, symbol, last_price_at}]}` |

## Holdings and transactions (holdings accounts)
| Method | Path | Body / notes |
|---|---|---|
| GET | `/accounts/{id}/holdings` | `Holdings` (below) |
| PUT | `/accounts/{id}/holdings/{instrument_id}` | `{units, avg_cost_gbp, as_of?}` → `ledger_service.set_position_target` |
| PUT | `/accounts/{id}/cash` | `{cash_gbp, as_of?}` |
| DELETE | `/accounts/{id}/holdings/{instrument_id}` | sets target units to 0 (keeps history) |
| GET | `/accounts/{id}/transactions?from&to&type&status&limit=100&offset=0` | `{items: Transaction[], total}` |
| POST | `/accounts/{id}/transactions` | `TransactionCreate`; 422 with the `LedgerError` message if invalid |
| PATCH, DELETE | `/transactions/{id}` | positions rebuilt; snapshots rebuilt from the earliest affected date |
| GET | `/transactions/pending` | pending rows across accounts, oldest first |
| POST | `/transactions/confirm` | `{items: [{id, units?, amount_gbp?, price_native?}]}` → confirms, applying edits |

`Holdings`:
```json
{
  "account_id": 3, "as_of": "2026-09-15T13:45:00Z", "cash_gbp": 12.40,
  "positions": [{
    "instrument": {"id": 1, "symbol": "VUSA.L", "name": "Vanguard S&P 500 UCITS ETF", "asset_class": "equity",
                   "quote_currency": "GBp", "price_source": "yahoo"},
    "units": 120.0, "avg_cost_gbp": 84.00, "cost_basis_gbp": 10080.00,
    "price_gbp": 97.31, "price_at": "2026-09-15T13:30:00Z", "is_stale": false,
    "value_gbp": 11677.20, "gain_gbp": 1597.20, "gain_pct": 0.1585,
    "day_change_gbp": 43.20, "day_change_pct": 0.0037, "weight": 0.2422
  }],
  "totals": {"value_gbp": 48210.55, "cost_basis_gbp": 41000.00, "gain_gbp": 7210.55, "gain_pct": 0.1759,
             "day_change_gbp": 212.40, "day_change_pct": 0.0044},
  "warnings": []
}
```
`TransactionCreate`: `{date, type, instrument_id?, units?, price_native?, currency?, fx_gbp_per_unit?,
amount_gbp, fees_gbp?, cost_basis_gbp?, split_ratio?, contribution_source?, notes?}`. The UI form
computes `amount_gbp` for BUY/SELL as `-(units × price × fx + fees)` / `+(units × price × fx − fees)`.

## Recurring plans
| Method | Path | Body / notes |
|---|---|---|
| GET | `/recurring?account_id&person_id` | `RecurringPlan[]` with `allocations` and `next_date` |
| POST | `/recurring` | `{account_id, name, kind, amount_gbp, frequency, day_of_month?, start_date, end_date?, annual_increase_rate?, contribution_source?, tax_relief_rate?, auto_record?, allocations?: [{instrument_id, weight}]}` |
| PATCH, DELETE | `/recurring/{id}` | |
| GET | `/recurring/upcoming?days=60&person_id` | `[{date, plan_id, account_id, name, kind, amount_gbp, gross_amount_gbp}]` (loan payments: `plan_id` null, `kind` `loan_payment`) |

## Net worth
| Method | Path | Returns |
|---|---|---|
| GET | `/networth/current?person_id` | `NetWorthCurrent` (below) |
| GET | `/networth/history?person_id&from&to&granularity=day\|week\|month&group_by=category\|account\|person` | `{dates: [], total: [], series: [{key, label, values: []}]}` (week/month = last snapshot in period) |
| GET | `/networth/attribution?person_id&from&to` | Phase 7: `{start_gbp, end_gbp, contributions_gbp, market_gbp, debt_paydown_gbp, revaluation_gbp, other_gbp}` |
| GET | `/allowances?tax_year=2026&person_id` | `[{person_id, name, tax_year, tax_year_end, days_left, isa_used, isa_limit, isa_remaining, lisa_…, jisa_…, pension_used, pension_limit, pension_remaining, is_estimated}]` |
| POST | `/snapshots/rebuild` | `{account_id?, from_date}` → `{job_id}`; `GET /jobs/{job_id}` → `{status, progress, error?}` |

`NetWorthCurrent`:
```json
{
  "as_of": "2026-09-15T13:45:00Z", "person_id": null,
  "total_gbp": 512345.67, "assets_gbp": 745000.10, "liabilities_gbp": -232654.43,
  "liquid_gbp": 98410.00, "illiquid_gbp": 413935.67,
  "changes": {
    "day":   {"abs_gbp": 1234.50, "pct": 0.0024},
    "week":  {"abs_gbp": -820.10, "pct": -0.0016},
    "month": {"abs_gbp": 6410.00, "pct": 0.0127},
    "ytd":   {"abs_gbp": 40112.00, "pct": 0.0849},
    "year":  {"abs_gbp": 51200.00, "pct": 0.1110}
  },
  "by_category": [{"category": "investment", "value_gbp": 98200.00, "share_of_assets": 0.1318}],
  "by_person": [{"person_id": 1, "name": "James", "color": "#2a78d6", "value_gbp": 301200.00}],
  "by_asset_class": [{"asset_class": "equity", "value_gbp": 180400.00}],
  "accounts": ["AccountSummary…"],
  "top_movers": [{"instrument_id": 1, "symbol": "VUSA.L", "name": "…", "day_change_gbp": 43.20, "day_change_pct": 0.0037}],
  "freshness": {"prices_updated_at": "2026-09-15T13:30:00Z", "stale_accounts": [{"account_id": 9, "name": "Nationwide Flex", "days_since": 41, "staleness": "warn"}]},
  "pending_transactions": 2
}
```
`changes.*` compare today's live total with the snapshot total on the reference date (yesterday,
7 days ago, one month ago, 31 Dec last year, one year ago); `null` when no snapshot exists yet.

## Projections and scenarios
| Method | Path | Body / notes |
|---|---|---|
| GET | `/projection?person_id&scenario_id&months=360&real_terms=false&by_account=false` | `{dates, total, by_category, by_person, by_account?, contributions, milestones: [{kind, label, date, person_id?}], assumptions}` |
| GET | `/projection/monte-carlo?person_id&scenario_id&months=360&real_terms=false` | `{dates, p10, p25, p50, p75, p90, deterministic, paths}`: percentiles of the total over 1,000 simulated paths; `deterministic` equals `/projection`'s `total`. `months` is 1–600 |
| POST | `/projection/compare` | `{scenario_ids, person_id?, months, real_terms}` → `{dates, series: [{scenario_id, name, total}]}` |
| GET, POST | `/scenarios` | `{name, return_adjustment, inflation_rate?, property_growth_rate?, notes?}` |
| PATCH, DELETE | `/scenarios/{id}` | cannot delete the default scenario |
| GET, POST | `/scenarios/{id}/events` | `{date, kind, account_id?, plan_id?, amount_gbp?, rate?, label}` |
| PATCH, DELETE | `/scenario-events/{id}` | |

Milestone kinds: `networth_target` (every £100k up to £2m plus goals), `mortgage_free`,
`pension_access` (per person: DOB + `pension_access_age`), `retirement` (DOB + retirement_age),
`fix_ends`, `scenario_event`.

## Settings and data
| Method | Path | Body / notes |
|---|---|---|
| GET | `/settings` | `{key: value}` for every key in `02-data-model.md` |
| PATCH | `/settings` | partial; validated per key |
| GET, PUT | `/tax-year-rules` | list / upsert rows |
| POST | `/backup` | runs a backup now → `{path}` |
| GET | `/backups` | `[{filename, size_bytes, created_at}]` |
| GET | `/export` | full JSON export of every table (Content-Disposition attachment) |
| GET, POST, PATCH, DELETE | `/goals` | Phase 7 |

Import endpoints (Phase 8) are specified in `06-imports-future.md`.

Trading 212 sync (PC only, not registered on the phone): `GET /trading212/links`,
`POST /trading212/links` (`{api_key, api_secret, environment, account_type: isa | invest, owner_person_id,
name?}`: checks the key, then creates the Stocks ISA / GIA holdings account and links it; nothing is
created when the key is rejected), `GET /trading212/links/{account_id}` (link or `null`), `PUT` (`{api_key, api_secret, environment}`;
checks the key against the account summary, 422 on a bad key or non-GBP account), `PATCH`
(`{auto_sync}`), `DELETE` (forgets the key; synced transactions stay) and
`POST /trading212/links/{account_id}/sync` (202, starts a background sync; poll the link's `status`),
`POST /trading212/sync` (202, syncs every link in the background; the Update prices button calls it),
`GET /trading212/changes` (syncs waiting to be accepted: `{account_id, account_name, batch_id, first_sync,
message, transactions, holdings, cash_before_gbp, cash_after_gbp, unmatched_instruments, ledger_warnings,
ready}`, no network) and `POST /trading212/links/{account_id}/accept` (commits the waiting sync,
replacing stand-ins for its holdings; 409 when nothing is waiting).
`AccountDetail.broker_sync` is `"trading212"` for a linked account.

## Sync (Phase 11)

`/api/sync/status`, `/api/sync/enabled`, `/api/sync/pair`, `/api/sync/devices/{id}` (PC) and
`/api/sync/client`, `/api/sync/client/pair`, `/api/sync/client/sync` (phone). The PC's
network-facing `/sync/v1/*` endpoints are a separate app on the sync port. Full contract in
`07-mobile.md`.
