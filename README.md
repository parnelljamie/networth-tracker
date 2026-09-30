# Waymark

**A private net worth tracker for UK households that runs entirely on your own computer.**

[![Latest release](https://img.shields.io/github/v/release/parnelljamie/networth-tracker?label=download)](https://github.com/parnelljamie/networth-tracker/releases/latest)
[![MIT licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![Buy me a coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/jparnell)

Waymark brings together your investments, pensions, cash, property, mortgages and other assets
and debts. It values them every day, keeps the history, and projects where the household is
heading, for one person or everyone together.

- **Private.** There's no cloud service, no account and no login. Everything is stored in one
  SQLite file on your own machine.
- **Free and open source**, under the [MIT licence](LICENSE).
- **Windows, Linux and Android.** The phone app syncs with your PC over your home Wi-Fi.

> [!IMPORTANT]
> **Waymark is not financial advice.** It is a record-keeping and estimation tool. Valuations,
> projections, allowances and tax figures are estimates based on what you enter, the assumptions
> you choose and third-party price data, and they can be wrong or out of date. Don't rely on them
> alone for decisions about investments, pensions, tax or borrowing; speak to a regulated financial
> adviser for that. The software is provided as is, without warranty of any kind (see [LICENSE](LICENSE)).

## Download

Get the latest version from the **[Releases page](https://github.com/parnelljamie/networth-tracker/releases/latest)**.
After that, the app updates itself from **Settings → Updates**.

### Windows 10 and 11

1. Download `WaymarkSetup-<version>.exe` and run it. It installs for your user only and needs no
   admin rights.
2. **Windows will probably warn you** with "Windows protected your PC". That's because the
   installer isn't code-signed, which costs money every year. Choose **More info**, then
   **Run anyway**. If you'd rather not, you can [build it yourself](#building-from-source) from this
   source code.
3. Waymark needs Microsoft Edge WebView2, which Windows 10 and 11 normally already have. The
   installer offers to open Microsoft's download page if yours doesn't.

During setup you can choose to have Waymark start in the background when you sign in, so the
nightly snapshot, price refreshes and backups happen even when you haven't opened it.

### Linux (Ubuntu 22.04+, Debian 12, Mint and other Debian-family distros, 64-bit)

```bash
sudo apt install ./waymark_<version>_amd64.deb
```

Waymark then appears in your app menu, or you can run `waymark` from a terminal. Run
`waymark --autostart on` to start it in the background when you log in, and
`waymark --autostart off` to stop that. The **Browse…** button for the backup folder needs
`zenity` (or `kdialog` on KDE).

### Android 8 or newer (64-bit ARM)

Download `waymark-<version>.apk` on the phone and open it. Android will ask you to allow installs
from your browser or file manager. The phone app is a companion to the PC app, mainly for viewing
with the odd balance or trade added on the go. **The PC holds the master copy.** See
[Phone sync](#phone-sync) below.

## Your data

| | Where it lives |
|---|---|
| Windows | `%APPDATA%\Waymark` (`C:\Users\<you>\AppData\Roaming\Waymark`) |
| Linux | `~/.local/share/Waymark` |
| Android | The app's private storage, never in Google's cloud backup |

This folder holds the database, backups and logs. **Settings → Data → Open folder** takes you there.

- **Backups.** Waymark backs itself up every night and whenever it closes. **Backup now** makes one
  on demand, and you can pick a second folder (OneDrive, for example) that every backup is also
  copied to.
- **Moving to a new PC.** Install Waymark on the new PC and close it. Then copy your old data
  folder over the new one and reopen Waymark.
- **Uninstalling** asks whether to delete your data, and keeping it is the default. On Linux,
  `sudo apt remove waymark` always leaves it in place.
- **Network use.** Waymark connects to Yahoo Finance for prices and exchange rates, to GitHub when you
  check for updates, and to Trading 212 only if you connect an account. Nothing else leaves your machine.

### Upgrading from Passbook

Waymark was called Passbook until version 0.5.2. You can upgrade from **Settings → Updates** as usual.
The new version moves your data from the old `Passbook` folder to `Waymark` the first time it opens,
and the installer replaces the old program, shortcuts and sign-in entry. Your phone keeps its
pairing, though Windows may ask once more whether to let Waymark through the firewall. On Linux, installing the `waymark` package removes the old `passbook` package.

## What it does

**Accounts and people**
- Several people (for example you, a partner, children), each with a date of birth and retirement
  age. Accounts can be owned jointly in any shares, and every figure can be viewed for one person or
  the whole household.
- Account types: investments (ISA, LISA, JISA, GIA), pensions (SIPP, workplace and defined benefit),
  cash, property, mortgages and loans, credit cards, and other assets or debts.
- Each account is valued in whichever way suits it:
  - **Holdings**: units × live price. Positions come from a transaction ledger (buys, sells,
    dividends, fees and so on), with average cost, gains and daily movers. Pence-quoted and
    foreign-currency instruments are converted to GBP.
  - **Balance**: the latest balance you entered, rolled forward by any regular payments since.
  - **Model**: a value that grows or depreciates at a set rate (a house, a car, a watch), drawn as a
    straight line between known valuations.
  - **Amortising**: mortgages and loans calculated from their terms, rate periods and overpayments.
  - **Defined benefit**: a DB pension valued as its accrued income × a capitalisation factor, with a
    Teachers' Pension Scheme preset.

**Pages**
- **Overview**: headline net worth (total or liquid only) with changes over the day, week, month,
  year to date and year. It has a history chart where each category can be shown or hidden, with
  every person's age under the date axis. It also shows allocation, liquidity and debt, the
  per-person split, today's movers, ISA allowance, upcoming regular payments and milestones.
- **Person**: the same view for one person, with their accounts.
- **Property & Mortgage**: value against mortgage balance, equity and loan-to-value, mortgage-free
  date, rate periods, the full amortisation schedule (exportable to CSV), an overpayment simulator,
  and property valuations alongside mortgage statement balances.
- **Pensions**: pots, monthly contributions (personal, employer, salary sacrifice, tax relief),
  annual allowance used, and projected pots at retirement.
- **Investments**: combined holdings, today's movers, ISA allowance, and history with a projection.
- **Other**: cash, debts and other assets.
- **Account pages**: history, holdings, transactions, balances, regular payments and settings.
  Holdings accounts also show their XIRR (money-weighted return).
- **Projections**: a month-by-month forecast up to 50 years ahead, by category or by person, in
  cash or today's money. Milestones mark being mortgage free, pension access, retirement and each
  £100k. It also shows values at key horizons and contributions against growth. You can compare
  three scenarios (base, optimistic, pessimistic) plus any you add. Each scenario can hold events
  such as lump sums, stopping or changing a payment, or changing a return rate. A
  **Range of outcomes** chart runs 1,000 simulated markets to show how far investment returns could
  move the result either way.
- **Goals**: targets for the household, a person, a category or an account, with progress and the
  projected date each is reached.
- **Import**: bring in a platform's full transaction history (a canonical CSV, template in
  `docs/import-templates/`) or a bank statement CSV. Each import shows a reconciliation before it is
  committed and can be undone.
- **Settings**: people, Trading 212, phone sync, data (backups, a second backup folder, JSON export),
  updates and about.

**Also**
- **Quick update**: one dialog for entering this month's balances in one go.
- **Trading 212**: paste an API key and Waymark pulls in that account's orders, dividends
  and cash movements. Any change to your holdings is shown for you to accept first. The key is
  stored outside the database, and on Windows it's encrypted to your user account.
- Command palette (`Ctrl+K`), privacy mode that hides every amount (`Shift+P`), and light and dark
  themes.
- A monthly change breakdown (contributions, market movement, debt paid off, revaluations), a
  check on cash held above the deposit protection limit, and stale-data warnings.

**Runs in the background**
| When | What |
|---|---|
| Every 15 minutes, weekdays 08:00–21:45 | Refresh prices and exchange rates |
| Daily at 07:00, and at startup | Record due regular payments as pending transactions to confirm |
| Daily at 22:15 | Take the day's snapshot of every account |
| Daily at 22:30, and when the app closes | Back up the database (and copy to a second folder if set) |
| At startup | Fill in any missed history days, fetching past prices where needed |

Prices come from Yahoo Finance through the unofficial [yfinance](https://github.com/ranaroussi/yfinance)
library. Yahoo allows this for personal use only and can change or block it at any time. If that
happens, prices stop updating until Waymark is fixed, and you can still enter prices by hand.

### Phone sync

When the phone and the PC are on the same Wi-Fi with Waymark open on the PC, the phone first sends
the PC anything you changed on it. It then takes a fresh copy of the PC's figures. It syncs when you
open the app, every 15 minutes while it's open, and when you tap the sync button in the menu.
Nothing goes through the cloud.

**Pairing (once):** on the PC, open Settings → Phone, turn on *Let phones sync with this PC* and
choose *Pair a phone*. On the phone, open Settings → Your PC and scan the code. The first time,
Windows asks whether to let Waymark through the firewall; allow it on private networks.

If the PC turns a change down (for example, selling units the PC has already sold), the phone tells
you what was dropped and why. Everything else still goes through.

## Support the project

Waymark is free and I build it in my spare time. If it's useful to you, you can
**[buy me a coffee](https://buymeacoffee.com/jparnell)** ☕. Thank you!

Found a bug or have an idea? [Open an issue](https://github.com/parnelljamie/networth-tracker/issues/new/choose).
Please don't post real balances, account numbers or API keys; made-up numbers that show the problem
are perfect. Security problems go through [private reporting](SECURITY.md) instead.

## Building from source

Needs [uv](https://docs.astral.sh/uv/) (Python 3.12) and Node 22 or newer. On Windows:
`winget install astral-sh.uv` and `winget install OpenJS.NodeJS.LTS`.

```powershell
cd backend; uv sync; cd ..
cd frontend; npm install; cd ..
./scripts/dev.ps1      # development: backend on :8000 with reload, Vite on http://localhost:5173
./scripts/start.ps1    # normal use: builds the frontend if needed and serves everything on http://127.0.0.1:8000
```

From source, data lives in `data/` in the repository (set `NW_DATA_DIR` to put it elsewhere).
`data/` is excluded from git, so personal financial data never goes into the repository.
`./scripts/install-autostart.ps1` registers the server to start hidden when you log on.

| Build | Command | Output |
|---|---|---|
| Windows installer | `./scripts/build-installer.ps1` (needs [Inno Setup](https://jrsoftware.org/isinfo.php)) | `dist/WaymarkSetup-<version>.exe` |
| Linux package | `./scripts/build-linux.sh` (on Linux) | `dist/waymark_<version>_amd64.deb` |
| Android app | `cd frontend; npm run build`, then `android/wheels/build-pydantic-core.sh android/wheels/dist` and `cd android; ./gradlew assembleDebug` (needs the Android SDK and NDK, Rust and Python 3.12) | `android/app/build/outputs/apk/` |

Set `SIGN_CERT_PATH` and `SIGN_CERT_PASSWORD` before `build-installer.ps1` to code-sign the Windows build.

**Checks.** Run `cd backend; uv run pytest; uv run ruff check .` and
`cd frontend; npm run typecheck; npm run lint; npm test; npm run build`. GitHub Actions runs all of
these on every push and pull request. It also fails if `frontend/src/api/schema.d.ts` is out of date
with the backend (regenerate it with `npm run gen:api` while the backend is running).
[CONTRIBUTING.md](CONTRIBUTING.md) lists the coding conventions.

### How it's built

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite, Alembic, APScheduler, yfinance, numpy |
| Frontend | React, TypeScript, Vite, Tailwind CSS with shadcn/ui, TanStack Query, Recharts |
| Desktop app | pywebview window (WebView2 on Windows, Qt WebEngine on Linux), packaged with PyInstaller and Inno Setup |
| Android | A WebView around the same backend, run on the phone with Chaquopy |

```
backend/app/
  engine/      pure financial maths, no database or clock: amortisation, ledger and average cost,
               growth, recurring dates, projections, Monte Carlo, XIRR, allowances, DB pensions
  services/    all database logic (valuation, snapshots, prices, loans, projections, imports, ...)
  api/         thin FastAPI routers, one per resource
  models/      SQLAlchemy tables; every change ships an Alembic migration
  providers/   price sources (Yahoo Finance, manual prices) and Trading 212
  jobs.py      the scheduled jobs above
frontend/src/
  pages/       one file per page
  components/  shared components, charts, and per-page parts (property/, account/)
  api/         generated API types and TanStack Query hooks
  lib/         formatting, dates and pure chart/series helpers
android/       the Android shell
scripts/       dev, start, autostart, installers, save/restore snapshots
packaging/     PyInstaller spec, Inno Setup script and Linux package files
docs/          design documents (below)
```

| Design doc | Covers |
|---|---|
| [01-architecture](docs/01-architecture.md) | Stack, folder layout, startup, scheduled jobs |
| [02-data-model](docs/02-data-model.md) | Every table, column and enum |
| [03-domain-logic](docs/03-domain-logic.md) | How each number is calculated |
| [04-api](docs/04-api.md) | The REST API |
| [05-ui](docs/05-ui.md) | Pages, design system and chart rules |
| [06-imports-future](docs/06-imports-future.md) | Transaction and bank CSV imports |
| [07-mobile](docs/07-mobile.md) | Android app and PC ↔ phone sync |
| [BUILD_PLAN](docs/BUILD_PLAN.md) | The phases the app was built in, and ideas for later |

### Saving and restoring a test setup

Two scripts snapshot a database and put it back. They're handy before a risky schema change or
after resetting the dev database.

```powershell
./scripts/save-my-data.ps1                                    # dev database -> snapshot "my-setup"
./scripts/save-my-data.ps1 -Source installed                  # the installed app's data folder instead
./scripts/restore-my-data.ps1                                 # snapshot "my-setup" -> dev database
./scripts/restore-my-data.ps1 -Target installed               # -> the installed app (close Waymark first)
```

Snapshots land in `data/snapshots/<name>/`. Each one has a SQLite online backup (`networth.db`),
a readable JSON dump and a manifest. Restoring first copies whatever it replaces into
`data/snapshots/_pre-restore/`. It also refuses to overwrite a database that a running app has open.
Snapshots contain real financial data, so keep them under the git-ignored `data/` folder.

### Releasing

Pushing a tag such as `v0.6.0` (matching `__version__` in `backend/app/__init__.py`) runs the
Release workflow. It builds the Windows installer, the Linux `.deb` and the signed Android APK from
the same commit. It then installs the `.deb` on Ubuntu 22.04, 24.04 and Debian 12 to check the app
starts, and attaches all three files to a GitHub Release on this repository. Settings → Updates
reads from that release. Running the workflow by hand from the Actions tab builds and tests
everything without publishing.

Repository secrets:
- `ANDROID_KEYSTORE_*` holds the Android signing key. Android only upgrades an app signed with the
  same key. `./scripts/setup-android-signing.ps1` creates the keystore (outside the repo) and sets
  the secrets. Back up the keystore and its password.
- `RELEASES_TOKEN` is a fine-grained token with Contents read/write on `parnelljamie/waymark-releases`.
  Installs from version 0.5.2 and earlier check that repo for updates, so each release is also
  copied there under the old Passbook file names. Once nobody is on those versions any more, this
  step can be dropped.

## Licence

[MIT](LICENSE) © 2026 Jamie Parnell. Waymark is not affiliated with Yahoo, Trading 212 or any
financial provider.
