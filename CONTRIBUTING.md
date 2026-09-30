# Contributing to Waymark

Thanks for your interest! Bug reports and ideas are very welcome as
[issues](https://github.com/parnelljamie/networth-tracker/issues/new/choose). If you'd like to send
code, please open an issue first so we can agree the approach before you spend time on it.

Never include real financial data (balances, account numbers, API keys, exports) in an issue, a
test or a commit. Made-up numbers are always fine.

## Where things are

| Doc | What it covers |
|---|---|
| `docs/01-architecture.md` | Stack, folder layout, processes, scheduler, how it runs on Windows |
| `docs/02-data-model.md` | Every table, column, enum and constraint |
| `docs/03-domain-logic.md` | Valuation, ledger, prices/FX, snapshots, mortgage, projections, allowances |
| `docs/04-api.md` | REST contract (paths, payloads, responses) |
| `docs/05-ui.md` | Pages, layout, components, design system, chart rules |
| `docs/06-imports-future.md` | Historical transaction and bank CSV import |
| `docs/07-mobile.md` | Android app, phone layout and PC ↔ phone sync |
| `docs/BUILD_PLAN.md` | The phases the app was built in, and ideas for later |

`backend/app/engine/` holds all the financial maths (amortisation, ledger/average cost, growth,
projections, recurring dates, FX/pence handling, XIRR, ISA allowance). It is pure and well tested.
Call it rather than re-implementing it, and never change a test's expected number to make code
pass. If you think the engine is wrong, open an issue with a worked example.

## Conventions

1. **Money** is GBP `float`. Round to 2 dp when persisting balances/transactions. Units are
   `float`, rounded to 8 dp. Compare to zero with `EPS = 1e-9` (units) / `0.005` (money).
2. **Rates are fractions everywhere in the backend and API**: `0.045` means 4.5%. Only the UI
   shows and accepts percentages (`PercentInput` divides by 100 on the way in).
3. **Liabilities are stored as positive amounts owed** (mortgage balance `185000.00`). The
   valuation layer makes them negative. Never store a negative mortgage balance.
4. **Dates** are `datetime.date` / ISO `YYYY-MM-DD`. **Timestamps** are UTC ISO-8601.
   "Today" always comes from `app.core.clock.today()` (Europe/London), never `date.today()`
   directly, so tests can freeze time. The engine never reads the clock; callers pass dates.
5. **Sync SQLAlchemy 2.0** (`Mapped[]`, `mapped_column`) and sync FastAPI endpoints (`def`, not
   `async def`). No async DB drivers.
6. Routers are thin: validate, call a service, return a schema. **All DB logic lives in
   `app/services/`**. Services call `app/engine/` for maths.
7. Every model change ships an **Alembic migration** (SQLite needs `render_as_batch=True`).
8. **Never call Yahoo/yfinance from a normal GET.** Only the price refresh job, the explicit
   `POST /api/prices/refresh`, instrument search and instrument creation touch the network.
9. After any backend schema or route change, regenerate the TypeScript client with
   `npm run gen:api` (in `frontend/`). Never hand-write API types.
10. Frontend: all server data goes through TanStack Query hooks in `src/api/hooks/`. All currency
    display goes through `<Money />`, all percentages through `<Pct />`, all formatting through
    `src/lib/format.ts`. No `toFixed` in components.
11. Holdings accounts are **ledger-first**: positions are derived from `transactions`. Editing
    units/avg cost in the UI writes an `OPENING_BALANCE` or `ADJUSTMENT` transaction via
    `ledger_service.set_position_target()`. Never write to `positions` directly; it is a cache.
12. Deleting an account cascades to its history (balances, transactions, positions, plans). The
    `is_archived` flag still exists and archived accounts are excluded from totals, but there is no
    archive control in the UI, so delete is the shipped path. `delete_person` still refuses while
    the person owns accounts; reassign or delete those first.
13. No new dependencies beyond `docs/01-architecture.md` without explaining why in the pull request.

## Commands

```powershell
# backend (from repo root)
cd backend; uv sync; uv run pytest; uv run ruff check .; uv run alembic upgrade head
# frontend
cd frontend; npm install; npm run typecheck; npm run lint; npm test; npm run build; npm run gen:api
# run everything for development
./scripts/dev.ps1
```

## Before you open a pull request

- `uv run pytest` and `uv run ruff check .` pass.
- `npm run typecheck`, `npm run lint`, `npm test` and `npm run build` pass.
- Anything a user can see has been tried in the running app, not just in tests.
- The description says what changed, what you left out, and anything in the docs that looked wrong.

By contributing you agree that your contribution is licensed under the project's [MIT licence](LICENSE).
