# 01 · Architecture

## What we are building

A private, local web app that tracks and projects household net worth:

- **Live S&S ISA / GIA / SIPP holdings** valued from internet prices (Yahoo Finance), using the
  units and average cost the user enters (later: derived from imported transactions).
- **Cash accounts** from manual entries or bank CSV imports.
- **Pensions** (holdings or pot value), with employee/employer contributions and tax relief.
- **Property and mortgage**: valuations, growth assumption, rate periods, overpayments and a
  full amortisation schedule.
- **Other assets and liabilities** that appreciate or depreciate at a set rate (car, watch, loan).
- **Multiple people** (me, partner, children) with joint ownership shares, plus a household view.
- **History**: a daily snapshot of every account, backfilled from price history when possible.
- **Projections**: month-by-month forecast from recurring plans and assumptions, with scenarios.

Single user, single machine, no cloud. Data lives in one SQLite file.

## Stack (pin these)

| Layer | Choice | Notes |
|---|---|---|
| Python | 3.12 via **uv** | `winget install astral-sh.uv`, then `uv python install 3.12`. Engine code is 3.10+ compatible. |
| API | FastAPI + Uvicorn | sync endpoints |
| ORM / DB | SQLAlchemy 2.0 + SQLite (WAL) | `data/networth.db` |
| Migrations | Alembic | `render_as_batch=True` for SQLite |
| Validation | Pydantic v2 + pydantic-settings | |
| Market data | yfinance + pandas | behind a `PriceProvider` interface |
| Scheduling | APScheduler **3.x** (`>=3.10,<4`) | v4 is a different API, do not use |
| Timezones | `zoneinfo` + **`tzdata`** package | Windows has no system tz database |
| Tests / lint | pytest, httpx, ruff | |
| Node | 22 LTS or newer | `winget install OpenJS.NodeJS.LTS` |
| UI | React + TypeScript + Vite | |
| Styling | Tailwind CSS + shadcn/ui | follow the official shadcn **Vite** install guide exactly; do not hand-write Tailwind config |
| Server state | TanStack Query | |
| Tables | TanStack Table (+ `@tanstack/react-virtual` for the mortgage schedule) | |
| Charts | Recharts via shadcn `chart` component | chart rules in `05-ui.md` |
| Forms | react-hook-form + zod (shadcn `Form`) | |
| Routing | react-router | |
| Misc | date-fns, lucide-react, sonner (toasts), cmdk (shadcn `Command`) | |
| API types | openapi-typescript + openapi-fetch | generated from FastAPI `/openapi.json` |
| Desktop window (Phase 7) | pywebview | optional: native window around the local site |
| Packaging (Phase 9) | PyInstaller (one-folder) + Inno Setup | `Waymark.exe` and a per-user `WaymarkSetup-<version>.exe` |

Current machine: Python 3.10 is installed, uv and Node are not. Install uv and Node first.

## Repository layout

```
NW Tracker Code/
├─ CONTRIBUTING.md
├─ docs/
├─ scripts/
│  ├─ dev.ps1            # runs uvicorn --reload on :8000 and vite on :5173
│  ├─ start.ps1          # builds frontend if needed, runs uvicorn on :8000, opens browser
│  └─ install-autostart.ps1  # Phase 7: Task Scheduler entry at logon (headless server)
├─ data/                 # gitignored: networth.db, backups/, logs/
├─ backend/
│  ├─ pyproject.toml
│  ├─ alembic.ini
│  ├─ alembic/versions/
│  ├─ app/
│  │  ├─ main.py         # FastAPI app, lifespan, router registration, SPA static serving
│  │  ├─ config.py       # Settings(BaseSettings): NW_DATA_DIR, NW_HOST, NW_PORT, NW_ENV
│  │  ├─ db.py           # engine, SessionLocal, get_db(), PRAGMAs, Base
│  │  ├─ core/
│  │  │  ├─ clock.py     # today(), now_utc() — patchable in tests
│  │  │  ├─ enums.py     # all StrEnum types from 02-data-model.md
│  │  │  └─ errors.py    # DomainError -> HTTP 422 handler
│  │  ├─ engine/         # PURE maths, provided + tested. No DB, no network, no clock.
│  │  ├─ models/         # SQLAlchemy models, one file per area
│  │  ├─ schemas/        # Pydantic request/response models
│  │  ├─ api/            # one router per resource (people.py, accounts.py, ...)
│  │  ├─ services/       # valuation, ledger, prices, snapshots, mortgage, projection,
│  │  │                  # recurring, allowances, backup, seed, importers/ (Phase 8)
│  │  ├─ providers/      # base.py (PriceProvider protocol), yahoo.py, manual.py
│  │  └─ jobs.py         # APScheduler setup + job functions
│  └─ tests/
│     ├─ engine/         # provided
│     ├─ services/
│     └─ api/
└─ frontend/
   ├─ package.json
   ├─ vite.config.ts     # alias @ -> src, proxy /api -> http://127.0.0.1:8000
   └─ src/
      ├─ main.tsx, App.tsx (router + layout)
      ├─ api/            # client.ts (openapi-fetch), schema.d.ts (generated), hooks/*.ts
      ├─ components/ui/  # shadcn generated
      ├─ components/     # app components (Money, Pct, DeltaChip, StatTile, charts/, tables/, dialogs/;
      │                  #   property/ cards and account/ tabs split out of their pages)
      ├─ pages/          # Overview, Person, AccountDetail, Property, OtherAssets, Projections, Import, Settings
      ├─ lib/            # format.ts, dates.ts, categories.ts (labels/icons/colours), utils.ts
      └─ styles/         # globals.css with design tokens
```

## Runtime

**Development**: `scripts/dev.ps1` starts `uv run uvicorn app.main:app --reload --port 8000`
in `backend/` and `npm run dev` in `frontend/`. Browse http://localhost:5173 (Vite proxies `/api`).

**Normal use**: `scripts/start.ps1` runs `npm run build` when `frontend/dist` is older than
`frontend/src`, then starts Uvicorn on `127.0.0.1:8000` and opens the browser. FastAPI serves
`frontend/dist` as static files with an SPA fallback (any non-`/api` path returns `index.html`).

**Always-on (recommended, Phase 7)**: register the server to start hidden at Windows logon so
the daily snapshot and price refresh run even when the UI is closed. On startup the app always
catches up any missed days, so this is a nicety, not a requirement.

Bind to `127.0.0.1` only. There is no login; do not expose to the network.

**Installed app (Phase 9)**: `Waymark.exe` starts the same server on a free local port and opens
it in a pywebview window. Data lives in `%APPDATA%\Waymark` instead of `data/`, so upgrades and
reinstalls never touch it. Resolve every file path through `app/core/paths.py`
(`resource_dir()`, `data_dir()`) from the start so this phase needs no path hunting.

**Linux build**: the same code and `packaging/waymark.spec` produce a `waymark` binary,
packaged as a `.deb` by `scripts/build-linux.sh` (installs to `/opt/waymark`). Data lives in
`~/.local/share/Waymark` (XDG). pywebview uses its Qt backend with PySide6 there, because Qt
WebEngine freezes into the build cleanly while the GTK/WebKit backend needs system libraries.
The folder picker uses `zenity`/`kdialog` instead of the Windows dialog, and
`waymark --autostart on|off` replaces the installer's sign-in registry entry. The Release
workflow (`.github/workflows/release.yml`) builds both platforms from one tag.

## Application lifecycle (`app/main.py` lifespan)

1. Ensure `data/`, `data/backups/`, `data/logs/` exist. Configure rotating file logging.
2. Run Alembic `upgrade head` programmatically.
3. `seed_service.ensure_defaults()`: default settings rows, tax-year rules, the `Base` scenario.
4. Start the APScheduler `BackgroundScheduler(timezone="Europe/London")`.
5. Submit `jobs.startup_job()` to a background thread (never block startup): `recurring_service.record_due()`, then `snapshot_service.catch_up()`.
6. On shutdown: `scheduler.shutdown(wait=False)`.

## Database setup (`app/db.py`)

- `create_engine("sqlite:///<data>/networth.db", connect_args={"check_same_thread": False})`
- On every connect: `PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`
- `SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)`
- `get_db()` dependency yields a session and closes it. Jobs open their own session.

## Scheduled jobs (`app/jobs.py`)

| Job | Trigger (Europe/London) | Does |
|---|---|---|
| `refresh_prices` | every `price_refresh_minutes` (default 15), Mon–Fri 08:00–21:30 | `price_service.refresh_quotes()` for held instruments + FX |
| `daily_snapshot` | daily 22:15 | refresh prices once more, write today's `account_snapshots` |
| `record_recurring` | daily 07:00 and at startup (before `catch_up`) | `recurring_service.record_due()` creates pending transactions/entries |
| `backup` | daily 22:30, and on app close | SQLite online backup to `data/backups/networth-YYYY-MM-DD.db`, keep newest N; also copied to the `backup_copy_dir` setting if set (a failed copy is logged, the local backup stands) |
| `catch_up` | once at startup | fill missing snapshot days, backfill price history for new instruments |

Every job: own DB session, `try/except` that logs and never raises, `max_instances=1`,
`coalesce=True`, `misfire_grace_time=3600`.

## Price provider boundary

```python
class PriceProvider(Protocol):
    def search(self, query: str) -> list[InstrumentSearchResult]: ...
    def metadata(self, symbol: str) -> InstrumentMetadata: ...          # name, currency, exchange, quote_type
    def quotes(self, symbols: list[str]) -> dict[str, Quote]: ...       # last, prev_close, bar_date
    def history(self, symbols: list[str], start: date, end: date) -> dict[str, list[DailyClose]]: ...
```

`YahooProvider` implements it with yfinance (details in `03-domain-logic.md` §3).
`ManualProvider` returns the instrument's stored manual price. Everything above the provider
works in GBP; the provider returns native prices and currency codes only.

## Logging and errors

- `logging` to `data/logs/app.log` (rotating 5 MB × 5) and console.
- Domain validation failures raise `DomainError(code, message, field=None)`; one exception
  handler maps it to HTTP 422 `{ "error": { "code", "message", "field" } }`.
- Network failures in price refresh never fail a request: the instrument keeps its last price
  and records `last_fetch_error`; the UI shows a stale badge.

## Dependencies

`backend/pyproject.toml` dependencies:
`fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `alembic`, `pydantic>=2`, `pydantic-settings`,
`yfinance`, `pandas`, `numpy`, `apscheduler>=3.10,<4`, `tzdata`, `python-multipart`.
Dev: `pytest`, `httpx`, `ruff`, `freezegun`.

`frontend/package.json` dependencies: `react`, `react-dom`, `react-router`, `@tanstack/react-query`,
`@tanstack/react-table`, `@tanstack/react-virtual`, `recharts`, `react-hook-form`, `zod`,
`@hookform/resolvers`, `date-fns`, `lucide-react`, `sonner`, `cmdk`, `openapi-fetch`, plus whatever
the shadcn CLI adds. Dev: `typescript`, `vite`, `@vitejs/plugin-react`, `tailwindcss`,
`openapi-typescript`, `eslint`, `vitest`.

Scripts: `"gen:api": "openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api/schema.d.ts"`,
`"typecheck": "tsc --noEmit"`.
