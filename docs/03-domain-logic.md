# 03 · Domain logic

How every number is produced. Services live in `backend/app/services/`; the maths they call is in
`backend/app/engine/` (already written and tested). Function names below are real.

---

## 1. Valuation (`valuation_service.py`)

`value_account(db, account, on: date, live: bool, *, with_net_contributions: bool = False) -> Valuation`

`net_contributions_gbp` is filled only for `holdings` accounts and only when
`with_net_contributions=True` (the snapshot writer): on the live path it costs a ledger
replay the positions cache would otherwise avoid.

```python
@dataclass
class Valuation:
    value_gbp: float            # signed: liabilities negative
    cost_basis_gbp: float | None
    net_contributions_gbp: float | None
    day_change_gbp: float | None
    is_estimated: bool
    detail: str | None          # e.g. "includes £400 expected contributions since 1 Sep"
```

`live=True` only for "today" reads from the API; snapshots of past dates use `live=False`.

| Method | Value on date `on` |
|---|---|
| `holdings` | `ledger.replay(confirmed_txns, as_of=on)`; for each held position `units × price_gbp(instrument, on, live)`; plus `cash_gbp`. Today (`live`) uses the `positions` cache and `accounts.cash_balance_gbp` instead of replaying. |
| `balance` | Latest `balance_entries` row on/before `on` (0 if none). If the account has active `contribution`/`withdrawal` plans, add `recurring.occurrences(plan, entry.date + 1 day, on)` (gross) and set `is_estimated` when any were added. |
| `model` | Latest entry on/before `on` (0 if none — never extrapolate back before the first valuation). **Between two known valuations, interpolate linearly**: with `later` = the first entry after `on`, `entry.balance + (later.balance − entry.balance) × (on − entry.date) / (later.date − entry.date)`. Only **after the last** entry does the growth model apply: `growth.value_on(entry.balance, entry.date, on, rate, method, floor, cap)`. `is_estimated = on > entry.date`. |
| `amortising` | Latest statement entry on/before `on`; `amortisation.build_schedule(terms, entry.balance, entry.date, actual_overpayments, until=on)` then `balance_on(rows, on, entry.balance)`. Estimated when rows were applied. |

Then: `sign = -1 if category in LIABILITY_CATEGORIES else 1`.

**Price for a date** (`price_service.price_gbp(instrument, on, live)`):
1. `price_source == manual` → the later-dated of `manual_price_gbp` (when `manual_price_date` is
   on/before `on`) and the latest `instrument_prices.close_gbp` on/before `on`; the typed price
   wins a tie. Neither is ever flagged stale — the user is the price source — except when nothing
   is dated on/before `on`, where `manual_price_gbp` is used as a stale fallback. This is what lets
   imported unit-price history (a pension statement's price per dealing date) value old snapshots
   at the price of the day instead of at today's typed figure. When `tracks_instrument_id` names a
   Yahoo instrument, that stated price is scaled by the tracked instrument's move from the stated
   date to `on` (its own price for `on`, live or not): e.g. pension units priced from statements
   follow the listed class of the same fund daily and snap back at each new statement. Day change
   is the tracked instrument's fractional day change applied to the scaled price.
2. `live` and `last_price_at` within 4 days → `last_price_gbp`.
3. Otherwise the latest `instrument_prices.close_gbp` on/before `on` within 10 days.
4. Otherwise the latest known price at all, flagged `is_stale` → valuation `is_estimated`.
5. No price at all → value 0 for that position and a warning string.

**Day change** (holdings): `Σ units × (last_price_gbp − prev_close_gbp)` for Yahoo instruments
whose `last_price_at` is today; others contribute 0.

**Scoping to people**
- `scoped_value = value × share(person)`; household = `value × Σ shares of people with include_in_household`.
- Accounts with `include_in_networth = false` appear in lists but not totals.
- `liquid_gbp` sums `is_liquid` accounts; a mortgage is illiquid with its property, so
  `illiquid_gbp` shows property equity rather than gross property value.

**Staleness**: `balance`/`model`/`amortising` accounts by days since the latest entry against
`settings.stale_balance_days` (`warn` 35, `alert` 90). Holdings: `warn` if any held price is older
than 3 days (4 over a weekend), `alert` if older than 10.

---

### `defined_benefit` (DB pensions, e.g. TPS)

Maths in `engine/db_pension.py`, DB glue in `db_pension_service.py`. From the statement figure at
`accrued_as_of`, month by month: **in service** (until the earlier of the owner's retirement age and
the scheme pension age) the pension grows by CPI + `revaluation_above_cpi` and gains
`accrual_rate × salary` a year (salary grows at `salary_growth_rate`); **deferred** it grows by CPI;
**in payment** (from the owner's date of birth + `normal_pension_age`) it rises by CPI. CPI is the
`inflation_rate` setting (the scenario's in projections). Value = yearly pension ×
`capitalisation_factor` + lump sum before payment starts, then pension × the factor's remaining
years. Always `is_estimated`. Projection kind `"db"` uses the same function per date.

## 2. Ledger (`ledger_service.py`)

Holdings accounts never store positions by hand. The flow:

```
transactions (confirmed) --engine.ledger.replay--> LedgerState --write--> positions cache + accounts.cash_balance_gbp
```

`rebuild_positions(db, account_id)`: load confirmed transactions, map rows to `engine.ledger.Txn`
(`id` = row id so same-day order is stable), `replay(strict=False)`, replace the account's
`positions` rows (skip `units <= EPS_UNITS`), write `cash_balance_gbp`, return `state.warnings`.
Call it after every create/update/delete/confirm of a transaction, inside the same DB transaction.

`validate_new(db, txn)`: `engine.ledger.validate_txn()` then replay the account's transactions plus
the new one with `strict=True`; turn `LedgerError` into `DomainError` (422) so an impossible sell
is rejected at entry time. Imports use `strict=False` and show warnings instead.

**`set_position_target(db, account_id, instrument_id, units, avg_cost_gbp, as_of=today)`** (the
inline "edit units / avg cost" in the holdings table):
1. Load confirmed transactions for the account.
2. If the only transactions for this instrument are a single `OPENING_BALANCE`, update that row in
   place: `units = target`, `cost_basis_gbp = round(target_units × avg_cost, 2)`.
3. Else if there are none, insert `OPENING_BALANCE` dated `as_of`, `source = opening`.
4. Else `du, dc = engine.ledger.position_target_adjustment(replay(txns), instrument_id, units, avg_cost)`;
   if `abs(du) > 1e-9 or abs(dc) > 0.005` insert `ADJUSTMENT(units=du, cost_basis_gbp=dc)` dated `as_of`.
5. `rebuild_positions`, then `snapshot_service.rebuild(account_id, from_date=as_of)` if `as_of < today`.

`set_cash_target` is the same with `cash_target_adjustment` and an instrument-less row.

When history is imported later (Phase 8), `OPENING_BALANCE` and `ADJUSTMENT` rows are exactly the
stand-ins that get replaced, see `06-imports-future.md`.

---

## 3. Prices and FX (`providers/yahoo.py`, `price_service.py`)

### Yahoo provider (yfinance)
- **Quotes, batched**: one call for all symbols (instruments + FX symbols):
  ```python
  df = yf.download(symbols, period="5d", interval="1d", group_by="ticker",
                   auto_adjust=False, actions=False, progress=False, threads=True, timeout=20)
  ```
  Columns are a MultiIndex `(symbol, field)`. For each symbol: `closes = df[symbol]["Close"].dropna()`;
  `last = closes.iloc[-1]`, `prev_close = closes.iloc[-2]` (or `last` if only one bar),
  `bar_date = closes.index[-1].date()`. During trading hours the last daily bar is the delayed
  intraday price. Handle a flat (non-MultiIndex) frame defensively.
- **History**: same call with `start=`, `end=` (end exclusive, so pass `end + 1 day`), chunks of 20 symbols.
- **Metadata** (once, when an instrument is created): `t = yf.Ticker(symbol)`;
  `t.fast_info.currency`, `t.fast_info.exchange`, `t.fast_info.quote_type`. Name from the search
  result or `t.info.get("longName") or t.info.get("shortName")`, wrapped in `try` because `.info`
  is slow and rate-limited. **Never call `.info` during refreshes.**
- **Search**: `yf.Search(query, max_results=10, news_count=0).quotes` → `symbol`, `shortname`/`longname`,
  `exchange`/`exchDisp`, `quoteType`. If `yf.Search` is unavailable, fall back to validating an exact
  symbol with `fast_info`. UK funds (OEICs) usually have Morningstar-style symbols like `0P0000XXXX.L`;
  searching by fund name or ISIN finds them.
- Wrap every call in `try/except Exception`, log, and return partial results. Yahoo throttles
  aggressive clients: never refresh more often than every 5 minutes, and back off (15 min → 1 h)
  after a rate-limit style failure.

### Normalisation (`engine.prices`)
```python
fx = {ccy: quotes[fx_symbol(ccy)].last for ccy in needed_currencies}   # e.g. {"USD": 0.7431}
price_gbp = to_gbp(q.last, instrument.quote_currency, fx)              # GBp -> ÷100, USD -> × rate
prev_gbp  = to_gbp(q.prev_close, instrument.quote_currency, fx)
price_gbp, fixed = fix_pence_glitch(price_gbp, instrument.last_price_gbp or prev_gbp)
```
`needed_currencies` = major currencies of held instruments other than GBP. Store each FX quote in
`fx_rates` for its bar date. `MissingFxRate` → keep the old price, set `last_fetch_error`.

### `refresh_quotes(db, force=False) -> RefreshResult`
1. Non-blocking module-level `threading.Lock`; if held return `already_running`.
2. Instruments = Yahoo instruments with a position in any non-archived account.
3. If not `force` and every one has `last_price_at` newer than `price_refresh_minutes` → `recent`.
4. Fetch quotes (instruments + FX) in one provider call.
5. Per instrument: normalise, write `last_price_native/gbp`, `prev_close_gbp`, `last_price_at = now_utc`,
   clear `last_fetch_error`; upsert `instrument_prices(bar_date, close_native, close_gbp, 'yahoo')`.
   Missing symbol → `last_fetch_error = "no data"`.
6. Commit, return counts and failures.

### History backfill (`ensure_history(db, instrument_ids, start, end)`)
Find missing trading ranges per instrument (compare against existing `instrument_prices` dates;
ignore weekends), fetch history in chunks, normalise each close with the FX close for the same date
(forward-fill FX up to 5 days), upsert. New instruments get 5 years in the background.

---

## 4. Snapshots and history (`snapshot_service.py`)

- **`take(db, on)`**: for every non-archived account with any data, `value_account(on, live=(on == today))`
  → upsert `account_snapshots(account_id, on)` with `source = daily`.
- **`catch_up(db)`** (startup): `last = max(date)`; if none, `take(today)` and stop. Else
  `ensure_history(held instruments, last + 1, today)`, then for each missing date `d` in
  `last + 1 .. today - 1` write snapshots with `live=False, source=backfill`; finally `take(today)`.
  For holdings accounts use `engine.ledger.replay_series(txns, dates)` once per account rather than
  replaying per day.
- **`rebuild(db, account_id, from_date)`**: delete that account's snapshots from `from_date` and
  recompute to today (`source = rebuild`). Triggered in a background thread by any backdated
  transaction, balance entry, rate period, overpayment or growth-model change. Coalesce requests per
  account (keep the earliest `from_date`).
- Calendar days, weekends included (prices carry forward), so charts have no gaps.
- **History endpoint**: `SELECT date, category, SUM(value_gbp × scope_share)` grouped by date and
  the `group_by` key, restricted to `include_in_networth` accounts. For `week`/`month` take the last
  date in each period. Ownership shares are the *current* shares (documented limitation).
- **Changes** (`day`, `week`, `month`, `ytd`, `year`): live total now minus total on the reference
  date (nearest snapshot on or before it); `pct = abs / |reference total|`.

---

## 5. Mortgages and loans (`loan_service.py`)

`terms_for(account) -> engine.amortisation.LoanTerms` from `loan_details` + `loan_rate_periods`
(`payment_override_gbp` → `payment_override`).

- **Anchor** = latest `balance_entries` row (source `statement` or `manual`). If none, anchor on
  `original_amount_gbp` at `start_date`.
- **Actual overpayments** = `loan_overpayments` with `is_planned = false`.
- **Planned overpayments** = `is_planned = true` rows + occurrences of active `overpayment` plans
  from tomorrow to maturity.
- **Estimated balance today** = `balance_on(build_schedule(terms, anchor, anchor_date, actual, until=today), today, anchor)`.
- **Schedule endpoint**: rows from today's estimated balance with planned overpayments;
  `baseline` = same without planned overpayments; `summarise()` for payoff date and interest.
- **Simulate**: planned overpayments + `extra_monthly_gbp` as a monthly plan from next month +
  `lump_sums`; compare with baseline: `months_saved = baseline.n_payments − sim.n_payments`,
  `interest_saved = baseline.total_interest − sim.total_interest`.
- **Allowance warnings**: for each fixed rate period, split into 12-month windows from its start;
  allowed = `overpayment_allowance_rate × opening_balance` of the first row in the window; warn if
  the window's overpayments exceed it.
- **Equity** (property): `property value − Σ owed on loans with secured_on_account_id = property`;
  `ltv = owed / value`; per person = equity × that person's share of the property (shares of the
  mortgage are assumed to match; show a note if they differ).

---

## 6. Recurring plans (`recurring_service.py`)

`to_engine(plan) -> engine.recurring.Plan` (`amount_gbp`, `frequency`, `start_date`, `end_date`,
`day_of_month`, `annual_increase_rate`, `tax_relief_rate`).

**`record_due(db, today)`** for plans with `auto_record` and `is_active`:
- due dates = `occurrence_dates(plan, (last_recorded_date or start_date − 1 day) + 1 day, today)`.
- **Holdings account**, for each due date:
  - `DEPOSIT` of the gross amount, `contribution_source` from the plan, `status = pending`,
    `source = recurring`, `recurring_plan_id`. With `tax_relief_rate > 0` write two deposits: the net
    amount (`personal`) and the relief (`tax_relief`).
  - For each allocation: `BUY` with `amount_gbp = −gross × weight`, `units = gross × weight / price_gbp(on the due date)`,
    `status = pending`. No price → skip the BUY, leave the cash.
- **Other accounts**: nothing is written. `balance` valuations already add expected contributions
  (§1) and projections use the plan directly.
- Set `last_recorded_date = today`.

Pending transactions do not affect positions. The UI lists them for one-click confirmation with the
real units/price from the broker's confirmation.

**Upcoming** = occurrences in the next N days across active plans, plus each active loan/mortgage's
scheduled monthly payments (read off its amortisation schedule; `kind: "loan_payment"`,
`plan_id: null`), sorted by date.

---

## 7. Projections (`projection_service.py`)

Build engine inputs from the DB, call `engine.projection.project`, add milestones.

| Account | `ProjectionAccount.kind` | `value` | `annual_rate` |
|---|---|---|---|
| investment, pension (not db_pension) | `growth` | current valuation | `expected_return_rate` or the weighted `default_return_rates` by holdings asset class (`balance` method: `multi_asset`) |
| cash, credit_card with interest | `growth` (`scenario_adjustable=False`) | current valuation (abs) | `interest_rate` or `default_return_rates.cash` |
| property | `model` | current modelled value | scenario `property_growth_rate`, else the account's growth model, else `default_return_rates.property` |
| other_asset / other_liability (model) | `model` | current modelled value (abs) | growth model rate, floor, cap |
| mortgage, loan (amortising) | `loan` | estimated balance today | from `terms_for()` |
| db_pension, balance-method liabilities | `static` | current value (abs) | – |

- `annual_fee_rate` = account's fee. Owners = account shares.
- Flows: every active recurring plan → `ProjectionFlow(account_id, to_engine(plan), kind)`.
- Scenario events: `lump_sum` → `LumpSum`; `set_return_rate` → `RateChange`; `stop_plan` → set the
  engine plan's `end` to the event date; `change_plan_amount` → end the plan the day before and add
  a copy starting on the event date with the new amount.
- `Assumptions(inflation_rate = scenario or settings, return_adjustment = scenario, real_terms = query)`.
- Scope to a person by filtering `by_person[person_id]` (the engine already splits by share).
- **Milestones**: `first_date_reaching(total, target)` for each £100k step above today's total (up
  to £2m) and for goals; `mortgage_free` = `summarise(loan_schedules[id]).payoff_date` for each
  mortgage; `pension_access` and `retirement` from people's dates of birth; `fix_ends` from current
  rate periods; scenario events with labels.

---

## 8. Allowances (`allowances_service.py`)

Contributions for the tax year containing `on`:
- **Holdings accounts**: confirmed `DEPOSIT` transactions (`contribution_source` → `source`,
  `is_cash = category == cash`), owner = the account's single owner.
- **Balance accounts** with plans: `occurrences(plan, tax_year_start, on)` split into net (`personal`)
  and relief (`tax_relief`) parts; mark the result `is_estimated`.
- Rules from `tax_year_rules` (latest row with `tax_year_start <= year`) → `engine.allowances.AllowanceRules`.
- `engine.allowances.allowance_usage(contributions, on, rules, person_ids)`; `days_left = (tax_year_end - on).days`.

---

## 9. Insights (Phase 7)

- **Change attribution** for a period `[a, b]` per account: holdings accounts
  `market = Δvalue − Δnet_contributions`, `contributions = Δnet_contributions` (the ledger's net
  contributions, so shares transferred in or out count at cost); cash
  `contributions = Δvalue`; loans `debt_paydown = Δvalue` (value is negative, so paying down is
  positive); property/model `revaluation = Δvalue`; balance-method pensions `other = Δvalue`. Sum per scope.
- **Deposit protection**: group cash accounts by `provider` per person; flag totals above
  `deposit_protection_limit_gbp` (the user should treat banks sharing a licence as one provider).
- **XIRR** per holdings account: flows = −DEPOSIT, −TRANSFER_IN cash, +WITHDRAWAL, +TRANSFER_OUT cash,
  plus today's value as a positive flow; `engine.returns.xirr()`. Shares transferred in/out with no
  cash count at their value (cost basis in; average cost out). Under a year of history the figure
  is not annualised: `(1 + xirr) ^ (days / 365) − 1` since the first flow, labelled "since <date>".
  Show "n/a" when `None`.
- **Goals**: progress = scoped current value / target; projected hit date via `first_date_reaching`.

## 10. Monte Carlo (`engine/monte_carlo.py`, `projection_service.build_monte_carlo`)

Per growth account, monthly log-returns ~ Normal(`ln(1+r)/12 − σ²/24`, `σ/√12`) with `σ` from
`default_volatility` by asset class; one shared draw per asset class per month so equity accounts
move together. 1,000 paths with numpy, contributions as in the deterministic model, loans and model
assets deterministic. Return p10/p25/p50/p75/p90 of the total per month.

As built:
- Intervals are the projection's real date gaps (`dt` years), not a flat 1/12. `r` is exactly the
  deterministic rate for that interval (scenario adjustment, rate-change events, minus fees), so
  with `σ = 0` the result equals `/projection`.
- An account's volatility comes from its asset-class weights: holdings by current value, or
  `multi_asset` for balance-method investments/pensions. The shock is `Σ w_c σ_c Z_c` with the
  classes drawn independently, and the drift uses `σ_a² = Σ (w_c σ_c)²`.
- Cash, credit cards, property and other model assets, loans, DB pensions and static items follow
  their deterministic path in every simulation, so the band shows market risk only.
- A fixed seed keeps the band identical between page loads; results share the projection cache.

