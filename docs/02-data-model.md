# 02 · Data model

SQLite via SQLAlchemy 2.0. Every table has `id INTEGER PRIMARY KEY` unless a composite key is
stated, plus `created_at` / `updated_at` (UTC timestamps, server-set) unless marked *(no audit)*.
Types: `money` = REAL rounded to 2 dp · `units` = REAL rounded to 8 dp · `rate` = REAL fraction
(`0.045` = 4.5%) · `share` = REAL in (0, 1] · `date` = DATE · `ts` = UTC DATETIME.

Enums are Python `StrEnum`s in `app/core/enums.py`, stored as TEXT.

## Enums

| Enum | Values |
|---|---|
| `Category` | `investment`, `pension`, `cash`, `property`, `mortgage`, `loan`, `credit_card`, `other_asset`, `other_liability` |
| `Wrapper` | `none`, `isa`, `lisa`, `jisa`, `gia`, `sipp`, `workplace_pension`, `db_pension` |
| `ValuationMethod` | `holdings`, `balance`, `model`, `amortising` |
| `TxnType` | `OPENING_BALANCE`, `BUY`, `SELL`, `DEPOSIT`, `WITHDRAWAL`, `DIVIDEND`, `INTEREST`, `FEE`, `TAX`, `TRANSFER_IN`, `TRANSFER_OUT`, `SPLIT`, `ADJUSTMENT` |
| `ContributionSource` | `personal`, `employer`, `salary_sacrifice`, `tax_relief`, `government_bonus`, `transfer` |
| `TxnStatus` | `confirmed`, `pending` |
| `TxnSource` | `manual`, `opening`, `recurring`, `import` |
| `BalanceSource` | `manual`, `statement`, `valuation`, `csv`, `estimate` |
| `AssetClass` | `equity`, `bond`, `multi_asset`, `property`, `commodity`, `cash`, `crypto`, `other` |
| `PriceSource` | `yahoo`, `manual` |
| `GrowthMethod` | `compound`, `linear` |
| `RepaymentType` | `repayment`, `interest_only` |
| `OverpaymentEffect` | `reduce_term`, `reduce_payment` |
| `RateType` | `fixed`, `tracker`, `variable`, `svr` |
| `PlanKind` | `contribution`, `withdrawal`, `overpayment` |
| `Frequency` | `weekly`, `fortnightly`, `monthly`, `quarterly`, `annually` |
| `SnapshotSource` | `daily`, `backfill`, `rebuild` |
| `ScenarioEventKind` | `lump_sum`, `stop_plan`, `change_plan_amount`, `set_return_rate` |

**Liability categories**: `mortgage`, `loan`, `credit_card`, `other_liability`.

### Allowed combinations (enforce in `account_service.validate()`)

| Category | Wrappers | Valuation methods (default first) | Liquid by default |
|---|---|---|---|
| investment | `isa`, `lisa`, `jisa`, `gia` | `holdings`, `balance` | yes (`lisa`, `jisa`: no) |
| pension | `sipp`, `workplace_pension`, `db_pension` | `holdings`, `balance` (`db_pension`: `defined_benefit` or `balance`; `defined_benefit` is `db_pension` only) | no |
| cash | `none`, `isa`, `lisa`, `jisa` | `balance` | yes (`lisa`, `jisa`: no) |
| property | `none` | `model` | no |
| mortgage | `none` | `amortising`, `balance` | no |
| loan | `none` | `amortising`, `balance` | yes |
| credit_card | `none` | `balance` | yes |
| other_asset | `none` | `model`, `balance` | no |
| other_liability | `none` | `model`, `balance`, `amortising` | yes |

Wrapped accounts (`isa`, `lisa`, `jisa`, `sipp`, `workplace_pension`, `db_pension`) must have
**exactly one owner with share 1.0**. A `db_pension` using `balance` defaults to `include_in_networth = false`;
one using `defined_benefit` (capitalised value) defaults to `true`.

---

## People and accounts

### `people`
| Column | Type | Notes |
|---|---|---|
| name | TEXT, unique, not null | "James" |
| color | TEXT | hex, from the categorical palette slots in `05-ui.md` |
| date_of_birth | date, null | enables pension-access and retirement milestones |
| retirement_age | INTEGER, default 67 | |
| include_in_household | BOOL, default true | false for e.g. a child whose JISA you track separately |
| sort_order | INTEGER, default 0 | |
| is_archived | BOOL, default false | |

### `accounts`
| Column | Type | Notes |
|---|---|---|
| name | TEXT, not null | "Trading 212 S&S ISA" |
| category | Category | |
| wrapper | Wrapper, default `none` | |
| valuation_method | ValuationMethod | see allowed combinations |
| provider | TEXT, null | platform / bank / lender, used for grouping and FSCS check |
| include_in_networth | BOOL, default true | |
| is_liquid | BOOL | default from the table above, user-overridable |
| expected_return_rate | rate, null | growth accounts; null → settings default by asset mix |
| annual_fee_rate | rate, default 0 | platform fee + fund OCF, deducted in projections |
| interest_rate | rate, null | cash accounts, credit cards |
| cash_balance_gbp | money, default 0 | **cache** for holdings accounts, written only by `ledger_service` |
| opened_date | date, null | |
| closed_date | date, null | |
| notes | TEXT, null | |
| sort_order | INTEGER, default 0 | |
| is_archived | BOOL, default false | |

### `account_owners` *(composite PK: account_id, person_id; no audit)*
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | |
| person_id | FK people | |
| share | share | shares per account must sum to 1.0 (±1e-6) |

---

## Observations: balances, valuations, growth models

### `balance_entries`
The single "point-in-time value" mechanism for `balance`, `model` and `amortising` accounts:
cash balances, pension pot values, property valuations, mortgage statement balances, car values.
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | |
| date | date | unique with account_id (same-day entry upserts) |
| balance_gbp | money, ≥ 0 | liabilities: positive amount owed |
| source | BalanceSource, default `manual` | |
| notes | TEXT, null | e.g. "Zoopla estimate", "Annual statement" |

### `growth_models` *(PK: account_id)*
Used by `model` accounts (property, other assets, some other liabilities).
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts, PK | |
| annual_rate | rate | `+0.03` appreciates, `-0.15` depreciates |
| method | GrowthMethod, default `compound` | |
| floor_value_gbp | money, null | depreciating assets never model below this |
| cap_value_gbp | money, null | appreciating assets never model above this |

### `property_details` *(PK: account_id)*
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts, PK | category `property` |
| address | TEXT, null | |
| purchase_date | date, null | |
| purchase_price_gbp | money, null | also written as the first `balance_entries` row (source `valuation`) |
| is_main_residence | BOOL, default true | |

---

### `db_pension_details` *(PK: account_id)*

Scheme terms for a `defined_benefit` pension, from the member's latest benefit statement.

| column | type | notes |
|---|---|---|
| account_id | FK accounts, CASCADE | |
| scheme | TEXT, default `tps_2015` | `tps_2015` preset or `custom` |
| accrued_annual_pension_gbp | money | yearly pension built up at `accrued_as_of` |
| accrued_lump_sum_gbp | money, default 0 | separate automatic lump sum (older final-salary sections) |
| accrued_as_of | date | statement date |
| accrual_rate | rate | TPS 2015: 1/57 of each year's pensionable salary |
| revaluation_above_cpi | rate, default 0 | in-service revaluation on top of CPI; TPS 2015: 0.016 |
| pensionable_salary_gbp | money, default 0 | yearly, at `accrued_as_of` |
| salary_growth_rate | rate, default 0 | |
| normal_pension_age | INTEGER | TPS 2015: State Pension age (68 if born after 5 Apr 1978) |
| is_active_member | BOOL, default true | false = deferred: no new accrual, CPI revaluation only |
| capitalisation_factor | REAL, default 20 | net-worth value = yearly pension × factor (+ lump sum) |

## Loans and mortgages

### `loan_details` *(PK: account_id)*
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts, PK | category `mortgage` / `loan` / `other_liability` |
| secured_on_account_id | FK accounts, null | mortgage → property account (for LTV/equity) |
| lender | TEXT, null | |
| original_amount_gbp | money, null | |
| start_date | date, null | |
| maturity_date | date, not null | date of the final scheduled payment |
| repayment_type | RepaymentType, default `repayment` | |
| payment_day | INTEGER 1–28, default 1 | |
| overpayment_effect | OverpaymentEffect, default `reduce_term` | |
| overpayment_allowance_rate | rate, default 0.10 | warning threshold per year during fixed periods |
| fallback_rate | rate, not null | assumed rate once all rate periods have ended (SVR or expected remortgage rate) |

### `loan_rate_periods`
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | |
| start_date | date | |
| end_date | date, null | inclusive; null = open-ended |
| annual_rate | rate | |
| rate_type | RateType | |
| label | TEXT, null | "5-year fix, Nationwide" |
| payment_override_gbp | money, null | when the lender's quoted payment should be used instead of the annuity formula |
| erc_rate | rate, null | early repayment charge, informational |

Periods for one account must not overlap (validate on write).

### `loan_overpayments`
One-off overpayments. Regular ones are `recurring_plans` with kind `overpayment`.
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | |
| date | date | |
| amount_gbp | money > 0 | |
| is_planned | BOOL | true = future what-if kept for projections; false = actually paid |
| notes | TEXT, null | |

Rule: an actual overpayment dated on/before the latest statement balance is already inside that
balance and is ignored by the schedule builder.

---

## Investments

### `instruments`
| Column | Type | Notes |
|---|---|---|
| symbol | TEXT, unique | Yahoo symbol (`VUSA.L`, `0P0000TKZO.L`, `AAPL`) or `MANUAL:<slug>` |
| name | TEXT | |
| isin | TEXT, null | |
| exchange | TEXT, null | |
| quote_type | TEXT, null | `ETF`, `EQUITY`, `MUTUALFUND`, `CRYPTOCURRENCY` |
| quote_currency | TEXT | exactly as the provider reports it: `GBp`, `GBP`, `USD`, `EUR` |
| asset_class | AssetClass, default `equity` | drives allocation charts and default returns |
| price_source | PriceSource | |
| manual_price_gbp | money-ish REAL, null | used when `price_source = manual` |
| manual_price_date | date, null | |
| tracks_instrument_id | FK instruments, null, `ON DELETE SET NULL` | manual only: a Yahoo instrument whose moves carry the stated price forward (03 §1) |
| last_price_native | REAL, null | cache written by `price_service` |
| last_price_gbp | REAL, null | cache |
| prev_close_gbp | REAL, null | cache, for day change |
| last_price_at | ts, null | |
| last_fetch_error | TEXT, null | |

Prices are REAL with up to 6 dp (fund prices can have 4+ dp). Do not round to 2 dp.

### `instrument_prices` *(PK: instrument_id, date; no audit)*
| Column | Type | Notes |
|---|---|---|
| instrument_id | FK instruments ON DELETE CASCADE | |
| date | date | exchange trading date of the bar |
| close_native | REAL | |
| close_gbp | REAL | after pence scaling and FX |
| source | PriceSource | |

### `fx_rates` *(PK: currency, date; no audit)*
| Column | Type | Notes |
|---|---|---|
| currency | TEXT | major unit, e.g. `USD` |
| date | date | |
| gbp_per_unit | REAL | GBP value of 1 unit (from Yahoo `USDGBP=X`) |

### `transactions`
The ledger for `holdings` accounts. Sign rules and effects are in `03-domain-logic.md` §2.
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | |
| instrument_id | FK instruments, null | required for BUY, SELL, SPLIT, TRANSFER_* of units, instrument OPENING_BALANCE/ADJUSTMENT |
| date | date | trade date |
| type | TxnType | |
| units | units, default 0 | always ≥ 0 except ADJUSTMENT (signed delta) |
| price_native | REAL, null | informational for BUY/SELL |
| currency | TEXT, default `GBP` | of `price_native` |
| fx_gbp_per_unit | REAL, default 1 | |
| amount_gbp | money | **signed cash effect on the account** (BUY negative, SELL positive, …) |
| fees_gbp | money, default 0 | informational; already included in `amount_gbp` |
| cost_basis_gbp | money, default 0 | OPENING_BALANCE / TRANSFER_IN (≥ 0) and ADJUSTMENT (signed delta) only |
| split_ratio | REAL, null | SPLIT only, new units per old unit |
| contribution_source | ContributionSource, null | DEPOSIT / TRANSFER_IN only |
| status | TxnStatus, default `confirmed` | pending rows are ignored by positions until confirmed |
| source | TxnSource, default `manual` | |
| recurring_plan_id | FK recurring_plans, null | |
| import_batch_id | FK import_batches, null | Phase 8 |
| external_id | TEXT, null | dedupe hash for imports; unique with account_id when not null |
| notes | TEXT, null | |

Index: `(account_id, date)`.

### `positions` *(cache; PK: account_id, instrument_id; no audit)*
Rebuilt by `ledger_service.rebuild_positions(account_id)` after any transaction change. Never
edited directly.
| Column | Type |
|---|---|
| account_id | FK accounts ON DELETE CASCADE |
| instrument_id | FK instruments |
| units | units |
| cost_basis_gbp | money |
| realised_gain_gbp | money |
| first_date | date |
| updated_at | ts |

Rows with `units == 0` are deleted.

---

## Plans, history, scenarios

### `recurring_plans`
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | target account (ISA, pension, cash, mortgage) |
| name | TEXT | "Monthly ISA", "Employer pension" |
| kind | PlanKind | |
| amount_gbp | money > 0 | net amount paid by the person (before tax relief) |
| frequency | Frequency | |
| day_of_month | INTEGER 1–28, null | monthly/quarterly/annually; null → start_date's day |
| start_date | date | |
| end_date | date, null | |
| annual_increase_rate | rate, default 0 | applied on each anniversary of start_date |
| contribution_source | ContributionSource, default `personal` | |
| tax_relief_rate | rate, default 0 | `0.25` for relief at source (net £80 → gross £100) |
| auto_record | BOOL, default false | create pending transactions / balance estimates on each due date. Always false on a broker-synced account (see `broker_links`); the plan still drives projections |
| last_recorded_date | date, null | |
| is_active | BOOL, default true | |

### `recurring_plan_allocations` *(PK: plan_id, instrument_id; no audit)*
How a contribution into a holdings account is invested. Weights sum to 1.0. No rows = stays as cash.
| Column | Type |
|---|---|
| plan_id | FK recurring_plans ON DELETE CASCADE |
| instrument_id | FK instruments |
| weight | share |

### `account_snapshots` *(PK: account_id, date; no audit)*
One row per account per calendar day. Charts read only from here.
| Column | Type | Notes |
|---|---|---|
| account_id | FK accounts ON DELETE CASCADE | |
| date | date | |
| value_gbp | money | **signed**: liabilities negative |
| cost_basis_gbp | money, null | holdings accounts |
| net_contributions_gbp | money, null | holdings accounts, cumulative deposits − withdrawals ± transfers (shares at cost) |
| is_estimated | BOOL | stale price, rolled-forward loan or modelled value |
| source | SnapshotSource | |
| created_at | ts | |

### `scenarios`
| Column | Type | Notes |
|---|---|---|
| name | TEXT, unique | seeded: `Base` (is_default), `Optimistic` (+0.02), `Pessimistic` (−0.02) |
| is_default | BOOL | exactly one |
| return_adjustment | rate, default 0 | added to every growth account's return |
| inflation_rate | rate, null | null → settings |
| property_growth_rate | rate, null | null → each property's own rate |
| notes | TEXT, null | |

### `scenario_events`
| Column | Type | Notes |
|---|---|---|
| scenario_id | FK scenarios ON DELETE CASCADE | |
| date | date | |
| kind | ScenarioEventKind | |
| account_id | FK accounts, null | `lump_sum`, `set_return_rate` |
| plan_id | FK recurring_plans, null | `stop_plan`, `change_plan_amount` |
| amount_gbp | money, null | `lump_sum` (signed: + in, − out; + on a loan = overpayment), `change_plan_amount` (new amount) |
| rate | rate, null | `set_return_rate` |
| label | TEXT | shown as a milestone marker |

---

## Configuration

### `settings` *(PK: key)*
`key TEXT`, `value JSON`. Seeded defaults:

| Key | Default |
|---|---|
| `inflation_rate` | `0.025` |
| `default_return_rates` | `{"equity":0.06,"bond":0.035,"multi_asset":0.05,"property":0.03,"commodity":0.02,"cash":0.035,"crypto":0.0,"other":0.03}` |
| `default_volatility` | `{"equity":0.16,"bond":0.06,"multi_asset":0.11,"property":0.12,"commodity":0.18,"cash":0.0,"crypto":0.7,"other":0.1}` |
| `price_refresh_minutes` | `15` |
| `projection_horizon_years` | `30` |
| `projection_real_terms` | `false` |
| `stale_balance_days` | `{"warn":35,"alert":90}` |
| `pension_access_age` | `57` (verify: normal minimum pension age rises to 57 in April 2028) |
| `deposit_protection_limit_gbp` | `120000` (verify current FSCS limit) |
| `backup_keep` | `30` |
| `privacy_mode_default` | `false` |

Defaults are nominal expectations, not advice; the user edits them in Settings.

### `tax_year_rules` *(PK: tax_year_start INTEGER, e.g. 2026 = 2026/27)*
| Column | Default seeded for 2024, 2025, 2026 |
|---|---|
| isa_allowance_gbp | 20000 |
| lisa_allowance_gbp | 4000 |
| jisa_allowance_gbp | 9000 |
| cash_isa_limit_gbp | null (a lower cash ISA sub-limit has been announced from April 2027: verify and add a 2027 row) |
| pension_annual_allowance_gbp | 60000 |

When no row exists for a tax year, use the latest earlier row.

### Phase 7: `goals`
`name`, `target_gbp`, `target_date null`, `scope` (`household` | `person` | `account` | `category`),
`person_id null`, `account_id null`, `category null`.

### Phase 8: imports
`import_batches` (`kind`: transactions | balances, `account_id`, `profile_name`, `filename`,
`imported_at`, `rows_total`, `rows_imported`, `rows_skipped`, `status`: committed | rolled_back),
`import_profiles` (`name`, `kind`, `mapping JSON`, `header_signature`),
`instrument_aliases` (`alias`, `profile_name`, `instrument_id`; unique alias+profile).
Details in `06-imports-future.md`.

### Broker sync: `broker_links` *(PK: account_id)*

One row per holdings account whose transactions come from a broker API (Trading 212): `provider`
(`trading212`), `environment` (live | demo), `key_hint` (last 4 chars), `auto_sync`, `status`
(idle | running | synced | up_to_date | needs_review | error), `status_message`, `last_synced_at`,
`last_new_rows`, `pending_batch_id` → `import_batches` (SET NULL). The API key is **not** stored in
the database: it lives in `<data_dir>/secrets/trading212-<account_id>.key`, DPAPI-encrypted on
Windows, so it never reaches backups or the phone. Details in `06-imports-future.md`.

### Phase 11: sync

`sync_devices`, `sync_applied_ops` (PC) and `sync_outbox` (phone), plus the `sync_enabled` and
`sync_port` settings. Columns and rules in `07-mobile.md` "Data model additions".
