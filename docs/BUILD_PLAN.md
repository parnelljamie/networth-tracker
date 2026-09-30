# Build plan

Build in phases. After each phase: run the app, tick the acceptance
list yourself, check the diff did not modify `backend/app/engine/`, then commit.

## Phase 0: Tooling and skeleton

**Read**: `CONTRIBUTING.md`, `docs/01-architecture.md`, `docs/05-ui.md` (Design system, App shell).

Do these first, by hand, in PowerShell:
```powershell
winget install astral-sh.uv
winget install OpenJS.NodeJS.LTS
git init; git add -A; git commit -m "Spec and engine"
```

**Tasks**
1. Backend: `uv sync` using the existing `backend/pyproject.toml`. Create `app/main.py`, `config.py`,
   `db.py`, `core/clock.py`, `core/enums.py` (every enum in `02-data-model.md`), `core/errors.py`,
   `core/paths.py` (`resource_dir()`, `data_dir()`: every file path goes through these so Phase 9
   packaging works), and `GET /api/health`.
2. Alembic: `alembic init alembic`, `render_as_batch=True`, target metadata from `app.db.Base`,
   empty baseline revision. Lifespan per `01-architecture.md` (directories, logging, upgrade head,
   scheduler started with no jobs yet).
3. Run `uv run pytest`: the 56 provided engine tests must pass unchanged.
4. Frontend: Vite + React + TypeScript in `frontend/`; shadcn/ui via the official Vite guide; install
   the dependencies listed in `01-architecture.md`; design tokens in `styles/globals.css`.
5. App shell: sidebar, top bar, routes with placeholder pages, theme toggle, privacy toggle (store
   + `Shift+P`), `Money`, `Pct`, `DeltaChip`, `lib/format.ts` with vitest unit tests.
6. `gen:api` script, `src/api/client.ts`, health status dot in the sidebar footer.
7. `scripts/dev.ps1` and `scripts/start.ps1`; FastAPI serves `frontend/dist` with SPA fallback.

**Acceptance**
- [ ] `./scripts/dev.ps1` opens the shell on http://localhost:5173 in light and dark themes.
- [ ] Sidebar footer shows a green health dot from `/api/health`.
- [ ] `./scripts/start.ps1` serves the built app on http://127.0.0.1:8000 and refreshing a deep link (e.g. `/projections`) works.
- [ ] `uv run pytest` → 56 passed; `npm run typecheck`, `lint`, `build` pass.
- [ ] `formatGBP(-1234.5)` renders `−£1,234.50`; privacy mode hides it.

---

## Phase 1: People, accounts, balances, other assets, Overview v1

**Read**: `02` (Enums, People and accounts, Observations, Configuration) · `03` §1 (`balance`, `model`,
scoping, staleness) · `04` (People, Accounts, Balances, Growth models, Settings) · `05` (Overview,
Person, Account Balances/Settings tabs, Other assets, Quick update, Settings: People and Assumptions).

**Tasks**
1. Models + migration: `people`, `accounts`, `account_owners`, `balance_entries`, `growth_models`,
   `property_details`, `settings`, `tax_year_rules`. `seed_service.ensure_defaults()`.
2. `account_service.validate()`: allowed combinations table, wrapped-account single owner, shares
   sum to 1, category-specific sub-objects.
3. `valuation_service` for `balance` and `model` methods (plan roll-forward comes in Phase 5),
   person/household scoping, liquidity, staleness.
4. APIs: people, accounts (create with `initial_balance`, `growth_model`, `property`), balances,
   quick update + bulk, settings, `networth/current` (changes, movers and pending return `null`/empty).
5. Tests (`tests/services`, `tests/api`, SQLite in-memory or tmp file, frozen clock): joint split,
   liabilities negative, model value today, archived and excluded accounts not in totals, validation errors.
6. UI: Settings → People; **Add account** dialog (steps: category → wrapper → owners → valuation
   method → initial value / growth model / property details); Person page (Summary, Cash, Other
   tabs); Account page (Balances, Settings tabs); Other assets page; Quick update sheet; Overview v1
   (hero figure without chart, People card, Allocation donut, Liquidity tiles, Accounts table).

**Acceptance**
- [ ] Create two people. A joint current account of £2,000 at 50/50 shows £1,000 on each person page and £2,000 on the household.
- [ ] A car valued £20,000 exactly one year ago at −15%/yr compound shows £17,000 today (±£10).
- [ ] A £500 credit card balance lowers net worth by £500 and appears under Debts.
- [ ] Quick update saves three balances in one submit and the Overview updates without reload.
- [ ] An ISA cannot be given two owners (clear error message in the dialog).
- [ ] Privacy mode hides every figure including the sidebar total.

---

## Phase 2: Investments (instruments, live prices, ledger)

**Read**: `02` (Investments) · `03` §1 (`holdings`, price for a date, day change), §2, §3 ·
`04` (Instruments and prices, Holdings and transactions) · `05` (Account Holdings/Transactions tabs,
price status pill, Person Investments/Pensions tabs).

**Tasks**
1. Models + migration: `instruments`, `instrument_prices`, `fx_rates`, `transactions`, `positions`.
2. `providers/base.py` protocol, `providers/yahoo.py` exactly as `03` §3, `providers/manual.py`.
   Tests use a `FakeProvider`; **no network in tests**.
3. `price_service`: `refresh_quotes`, `price_gbp`, `ensure_history`; instrument creation with
   metadata and background 5-year history; in-memory search cache.
4. `ledger_service`: `rebuild_positions`, `validate_new`, `set_position_target`, `set_cash_target`,
   `confirm_pending`.
5. `holdings` valuation, day change, top movers in `networth/current`.
6. APIs per `04`; `refresh_prices` job registered with the scheduler.
7. Tests: a `GBp` instrument is valued in pounds; a `USD` instrument converts with FX; 100x glitch
   corrected; first edit updates the single `OPENING_BALANCE`, later edit writes `ADJUSTMENT`;
   oversell returns 422; holdings totals; refresh lock returns `already_running`.
8. UI: Holdings tab (inline edit, cash row, weights bars), instrument search + manual instrument
   dialog, Transactions tab + dialog, price pill + refresh button, Person Investments/Pensions tabs
   (account cards, combined holdings).

**Acceptance**
- [ ] Add `VUSA.L` with 100 units at £80 avg: value ≈ 100 × the price shown on Yahoo **in pounds** (not 100x).
- [ ] Add a US share (e.g. `AAPL`): value is converted to GBP.
- [ ] Edit units 100 → 110: the Transactions tab still shows one `OPENING_BALANCE` (110 units).
- [ ] Add a BUY, then edit avg cost in the table: an `ADJUSTMENT` row appears and positions match the typed values.
- [ ] Selling more units than held is refused with a readable message.
- [ ] Refresh prices updates "updated x ago"; with the network off the app still loads and shows stale badges.

---

## Phase 3: History, snapshots, scheduler, backups

**Read**: `01` (Scheduled jobs) · `03` §4 · `04` (account history, net worth history, snapshots
rebuild, backup) · `05` (Chart rules, Overview hero chart, Account History tab, sparklines).

**Tasks**
1. `account_snapshots` model + migration.
2. `snapshot_service.take/catch_up/rebuild` with a coalescing background worker; call `rebuild` from
   balance, transaction, growth model and (later) loan changes dated before today.
3. Jobs: `daily_snapshot`, `backup` (sqlite3 online backup, keep `backup_keep`), `catch_up` at startup.
4. Endpoints: `networth/history`, `changes` in `networth/current`, `accounts/{id}/history`,
   `snapshots/rebuild` + `jobs/{id}`, `backup`, `backups`.
5. UI: `ChartCard` (legend, table toggle), `AreaStackChart` (assets above zero, debts below, total
   line), `RangeFilter`, tooltips; Overview hero chart + change chips; Account History tab; person
   history; sparklines on cards.
6. Tests: catch-up fills missing days from price history; backdated balance triggers rebuild;
   aggregation by person uses shares; change calculations use the right reference dates.

**Acceptance**
- [ ] With the app closed for two days, starting it fills the missing days (check the History table view).
- [ ] A balance entry dated 60 days ago shows as a step at that date after a few seconds.
- [ ] Range buttons change every card on the Overview together.
- [ ] A dated backup file appears in `data/backups/` after "Backup now".

---

## Phase 4: Property and mortgage

**Read**: `02` (Loans and mortgages, `property_details`) · `03` §1 (`amortising`), §5 · `04` (Growth
models, property, loans) · `05` (Property & Mortgage page).

**Tasks**
1. Models + migration: `loan_details`, `loan_rate_periods`, `loan_overpayments`.
2. `loan_service`: `terms_for`, anchor, estimated balance today, schedule, simulate, allowance
   warnings, equity. Rate-period overlap validation.
3. `amortising` valuation; snapshot rebuild hooks for loan changes.
4. APIs per `04`.
5. UI: KPI row, value vs balance chart, overpayment simulator, rate-period timeline + table,
   virtualised schedule grouped by year with CSV export, valuations and statements tables.
6. Tests: schedule endpoint equals engine output; statement re-anchoring; planned vs actual
   overpayments; equity split by person.

**Acceptance**
- [ ] £200,000, 4.5%, 25 years from next month: monthly payment £1,111.66.
- [ ] A 2-year fix followed by a 6% fallback changes the payment on the first payment after the fix ends.
- [ ] Simulating £200/month extra shows an earlier mortgage-free date and interest saved; "Save as plan" persists it.
- [ ] Entering a new statement balance moves the estimated balance and schedule to start from it.
- [ ] Property page equity = valuation − mortgage, split correctly between owners.

---

## Phase 5: Pensions, recurring plans, allowances

**Read**: `02` (`recurring_plans`, allocations, `tax_year_rules`) · `03` §1 (balance roll-forward), §6,
§8 · `04` (Recurring plans, allowances, pending/confirm) · `05` (Pensions tab, Plans tabs, ISA
allowance card, pending bell, Coming up card).

**Tasks**
1. Models + migration: `recurring_plans`, `recurring_plan_allocations`.
2. `recurring_service`: validation (weights sum to 1; allocations only on holdings accounts;
   overpayment plans only on loans), `record_due` job (idempotent), `upcoming`.
3. Balance roll-forward of expected contributions in valuation.
4. `allowances_service` + endpoint.
5. UI: plan dialog with allocation editor, Plans tabs, pending confirmation popover, pension cards
   (contribution split, access date), ISA allowance meters, Coming up card.
6. Tests: `record_due` twice creates no duplicates; relief split into two deposits; pending ignored by
   positions until confirmed; allowances combine ledger deposits and estimated plans.

**Acceptance**
- [ ] A £500/month ISA plan split 80/20 with auto-record creates one deposit and two pending BUYs on the due date; confirming updates holdings.
- [ ] A £400 net SIPP plan with 25% relief shows £500/month gross going in.
- [ ] A pot-value-only pension shows "includes £X expected contributions since <date>" until a new balance is entered.
- [ ] The ISA card shows 2026/27 usage per person and days left.

---

## Phase 6: Projections and scenarios

**Read**: `02` (`scenarios`, `scenario_events`) · `03` §7 · `04` (Projections and scenarios) ·
`05` (Projections page, Overview projection toggle, Milestones card).

**Tasks**
1. Models + migration; seed Base, Optimistic (+2%), Pessimistic (−2%).
2. `projection_service` (mapping table, flows, events, milestones), compare endpoint, in-memory
   cache keyed by parameters + a data version bumped on every write.
3. UI: Projections page, Overview "Show projection" toggle, Milestones card, projected pension pot on pension cards.
4. Tests: account kind mapping; `stop_plan` and `change_plan_amount` events; person scoping;
   milestone dates.

**Acceptance**
- [ ] Moving the horizon slider redraws a 30-year projection in well under a second.
- [ ] The mortgage-free marker matches the payoff date on the Property page.
- [ ] "Today's money" lowers future values; Optimistic > Base > Pessimistic at 20 years.
- [ ] Adding a £10,000 lump-sum event to the ISA in 2030 lifts the line from that month.

---

## Phase 7: Polish and insights

**Read**: `03` §9 · `05` (command palette, privacy, empty states, Settings) · `02` (`goals`).

**Tasks**
1. Command palette (`Ctrl+K`), keyboard shortcuts, empty states and first-run onboarding.
2. Goals (model, API, UI with projected hit date).
3. Change attribution card: "This month: +£2,140 contributions, +£3,020 markets, +£610 mortgage paid".
4. Deposit protection check card; XIRR on holdings account pages; JSON export.
5. `scripts/desktop.py` (pywebview window on the local server) and `scripts/install-autostart.ps1`
   (Task Scheduler task at logon running the server hidden).
6. Accessibility pass: focus rings, table views for every chart, reduced motion.

**Acceptance**
- [ ] `Ctrl+K` → "quick" → Enter opens Quick update.
- [ ] The attribution card adds up to the month's net worth change.
- [ ] After logon the server runs without a window and the daily snapshot appears the next day.

---

## Phase 8: Historical imports

**Read**: `docs/06-imports-future.md` in full.

**Acceptance**
- [ ] A canonical CSV fixture imports with a correct reconciliation table.
- [ ] Commit replaces the opening-balance stand-ins and the history chart extends back to the first transaction.
- [ ] Rollback restores the previous holdings and history exactly.
- [ ] A newest-first bank CSV produces correct daily balances.

---

## Phase 9: Windows installer

Goal: a `WaymarkSetup-<version>.exe` that installs and runs on any Windows 10/11 PC with no
Python, Node or admin rights, keeps data safe across upgrades, and is built with one command.
Can be done before or after Phase 8; needs Phases 0–7 (the pywebview window exists).

**Read**: `01-architecture.md` (Runtime, Application lifecycle, Database setup) and this phase.

**Fixed decisions** (do not revisit)
- **PyInstaller one-folder build** (`--onedir`), not one-file: starts faster, fewer antivirus false
  positives, and the installer wraps the folder anyway. Build config lives in `packaging/waymark.spec`.
- **Entry point** `backend/app/launcher.py`; the frozen program is `Waymark.exe`.
- **Data folder**: `NW_DATA_DIR` if set; else `%APPDATA%\Waymark` when frozen (`getattr(sys, "frozen", False)`);
  else `<repo>/data` in development. Logs and backups live inside it. Nothing is written next to the exe.
- **Per-user install** to `{localappdata}\Programs\Waymark`, no admin prompt.
- **Inno Setup** for the installer (`winget install JRSoftware.InnoSetup`), script `packaging/waymark.iss`.
- **Single version source**: `__version__` in `backend/app/__init__.py`, shown in Settings, returned by
  `/api/health`, stamped into the installer file name.
- Code signing is optional and off by default.

**Tasks**
1. `app/core/paths.py`: `resource_dir()` (`sys._MEIPASS` when frozen, repo root otherwise) and
   `data_dir()` per the rule above. Replace every hard-coded path in `config.py`, `main.py` (static
   `frontend/dist`) and Alembic setup with these helpers.
2. Alembic when frozen: bundle `alembic.ini` and `alembic/` as data files; build the Alembic `Config`
   in code with an absolute `script_location`. Before upgrading a database that is behind head,
   copy it to `backups/networth-pre-upgrade-<version>.db`.
3. `app/launcher.py`:
   - Single instance: a lock file plus `data_dir()/server.json` (`port`, `pid`). If another instance
     answers `/api/health`, open a window on its port and exit instead of starting a second server.
   - Port: try `8765`, fall back to an OS-assigned free port; bind `127.0.0.1` only.
   - Start Uvicorn in a background thread (`uvicorn.Server(uvicorn.Config(app, host, port, log_config=None))`),
     poll `/api/health` for up to 20 s, then open a pywebview window (title "Waymark", 1280×840,
     min 1024×700). If health never answers, show a native message box pointing at the log file.
   - `--background` flag: run the server and scheduler with no window (used at sign-in so snapshots
     and backups happen). Opening Waymark from the Start menu while it runs attaches a window.
   - Closing the window exits the process unless it was started with `--background`.
4. `packaging/waymark.spec`: entry `backend/app/launcher.py`; `datas` for `frontend/dist`,
   `backend/alembic`, `backend/alembic.ini`; `collect_all("yfinance")`, `collect_data_files("tzdata")`,
   `collect_dynamic_libs("curl_cffi")`, `collect_submodules("apscheduler")`; hidden imports for
   `uvicorn.logging`, `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`, `uvicorn.protocols.websockets.auto`,
   `uvicorn.lifespan.on`; `console=False`; icon `packaging/waymark.ico`; version info from `__version__`.
5. `packaging/waymark.iss`:
   - fixed `AppId` GUID (so new versions upgrade in place), `PrivilegesRequired=lowest`;
   - Start menu shortcut, optional desktop shortcut;
   - optional task "Start Waymark in the background when I sign in" → `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
     value `Waymark` = `"{app}\Waymark.exe" --background` (removed on uninstall);
   - close a running Waymark before installing/uninstalling (`CloseApplications=yes`, plus killing the
     background process by its `server.json` pid if needed);
   - WebView2 check: if the Evergreen runtime is missing, offer to open Microsoft's download page;
   - uninstall asks "Also delete your Waymark data?" with **No** as the default; only on Yes remove
     `%APPDATA%\Waymark`.
6. `scripts/build-installer.ps1`: fail fast if `uv`, `npm` or `ISCC.exe` are missing; run backend tests
   and ruff; `npm ci; npm run build`; `uv run pyinstaller packaging/waymark.spec --noconfirm --clean`;
   run ISCC; write `dist/WaymarkSetup-<version>.exe` and print its SHA-256. If `SIGN_CERT_PATH` and
   `SIGN_CERT_PASSWORD` are set, sign both `Waymark.exe` and the installer with `signtool`; otherwise
   print "Unsigned build".
7. Dependencies: add `pyinstaller` to the backend dev group (and `pywebview` if Phase 7 has not).
   Inno Setup and signtool are machine tools, not project dependencies.
8. Settings → Data shows the app version and data folder path with an "Open folder" button.
9. `README.md`: an "Installing on another computer" section covering the SmartScreen prompt on unsigned
   builds ("More info → Run anyway"), where data lives, how to back up and move it, and that each
   computer keeps its own data.

**Acceptance** (test on a clean machine: Windows Sandbox on Windows 11 Pro gives one in a minute)
- [ ] `./scripts/build-installer.ps1` produces `dist/WaymarkSetup-<version>.exe` with no manual steps.
- [ ] On a PC without Python or Node, the installer runs without an admin prompt and Waymark opens from the Start menu within 15 seconds.
- [ ] Data is created under `%APPDATA%\Waymark`; nothing is written to the install folder.
- [ ] Prices refresh, a quick update saves, and the data is still there after closing and reopening.
- [ ] Opening Waymark twice does not start a second server.
- [ ] With something else listening on port 8765, Waymark still starts.
- [ ] With "start in the background" ticked, signing in starts no window, and the next day's snapshot and backup exist.
- [ ] Installing a newer version over an older one keeps all data, runs migrations and leaves a pre-upgrade backup.
- [ ] Uninstalling with the default answer keeps the data; reinstalling shows it again.
- [ ] Settings and `/api/health` show the same version as the installer file name.

Out of scope: automatic updates and syncing data between computers (see Phase 10).

---

## Phase 10: Stretch ideas

- ~~Monte Carlo fan chart on Projections (`03` §10).~~ Done: "Range of outcomes" card.
- UK House Price Index indexation for property valuations.
- Docker image for an always-on home server (add authentication before exposing it to a network).
- Open-banking balance feed behind a `BalanceFeedProvider` interface (check current aggregator
  availability, pricing and terms first; they change often).
- Automatic update check for the installed app (compare `__version__` with a release feed, offer
  to download the new installer).
- Sharing one household's data across computers: run Waymark on one always-on machine and open it
  from the others over the home network (requires adding a login first).

---

## Phase 11: Android app and phone sync

**Read**: `docs/07-mobile.md` in full · `05` (App shell, Design system) · `01` (Runtime, Scheduled jobs).

Build in this order; each part is shippable on its own and the desktop app must behave exactly as
before throughout (`NW_ROLE` defaults to `desktop`).

**11.1 Mobile layout**
1. `AppLayout`: below `md`, the sidebar becomes a drawer (shadcn `Sheet`, left) opened from a menu
   button in the top bar; it closes on navigation. Desktop layout unchanged.
2. `TopBar` compact mode: menu button, page title, icon-only refresh and Quick update, bell. Search
   and Add account move into the drawer.
3. Page pass at 390 × 844: page padding 16 px, grids to one column, tables scroll inside their card,
   no horizontal page scroll anywhere, dialogs full width.

**11.2 Sync backend**
1. `role` setting; phone-role id allocation (`before_insert`), outbox middleware and exclusions,
   423 while syncing. Migration `sync_tables`.
2. Desktop: `sync_devices`, pairing endpoints, the LAN sync server (`/sync/v1/hello|push|snapshot`)
   with token auth, and `apply.py` (idempotent, id remapping, per-op results).
3. Phone: `sync.json`, `client.sync_now()` with the database swap, `/api/sync/client*` endpoints,
   jobs trimmed for the phone role.
4. Tests from `07` §Tests.

**11.3 Sync UI**
1. Settings → **Phone**: turn syncing on, "Pair a phone" shows the QR code and the addresses,
   paired devices with last sync and Unpair.
2. Phone role: Sync row in the drawer, report dialog, "Changes waiting" count, pairing screen
   (scan or paste the pairing link). Import page and desktop-only Settings rows hidden.

**11.4 Android shell**
1. `android/` Gradle project: Kotlin `MainActivity` + WebView, Chaquopy with the backend's
   dependencies, `app/mobile.py` entry point, frontend `dist` bundled.
2. `YahooHttpProvider` for the phone role.
3. `.github/workflows/android.yml` builds a debug APK artifact.

**11.5 Release**
1. Release workflow: signed release APK attached to the GitHub Release.
2. README: installing on Android, pairing, what syncs and when.

**Acceptance**
- [ ] At 390 px wide every page is usable with no horizontal page scroll; desktop layout is unchanged at 1280 px.
- [ ] Pairing: the PC shows a QR code; scanning it on the phone pairs, and the PC lists the phone.
- [ ] Offline on the phone, add a balance entry and a BUY; back on home Wi-Fi with the PC on, Sync shows both applied and both appear on the PC.
- [ ] A new account created on the phone, with a balance entry on it, arrives on the PC as one account with that entry.
- [ ] A sell of more units than held, entered on the phone after the PC sold them, is reported as rejected with the PC's reason; nothing else is lost.
- [ ] Syncing twice in a row changes nothing the second time.
- [ ] With the PC off, the phone still opens, shows the last synced figures and refreshes prices.
- [ ] From another device on the network without the token, `/sync/v1/*` answers 401 and `/api/*` is not reachable at all.
- [ ] A release tag produces a signed APK next to the Windows installer and the `.deb`, and installing a newer APK over an older one keeps the pairing.
