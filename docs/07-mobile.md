# 07 · Android app and phone sync (Phase 11)

Waymark on an Android phone, kept in step with the Windows (or Linux) install on the home PC.
The phone is **mainly for viewing**, with the odd balance update or investment added on the go.

## Principles

1. **The PC is the master copy.** Its database is the only one that is ever authoritative. The
   phone holds a copy of it plus a list of the changes made on the phone since the last sync.
2. **The phone never merges databases.** A sync is: send the phone's changes to the PC, the PC
   applies them through its normal API (so the same validation runs), then the phone replaces
   its copy with a fresh one from the PC.
3. **One codebase.** The phone runs the same FastAPI backend and the same React UI as the PC,
   embedded in an Android app. Nothing in `backend/app/engine/` or the services is forked.
4. **Home Wi-Fi only.** No cloud, no relay. The two devices sync when both are on the same
   network. Pairing is a one-off QR scan. No financial data ever goes to GitHub or any service.

## Roles

`NW_ROLE` (pydantic setting `role`) is `desktop` (default, every existing install) or `phone`.

| | desktop | phone |
|---|---|---|
| Records its API changes in the outbox | no | yes |
| New row ids | normal (`max + 1`) | from `PHONE_ID_BASE = 2**40` up |
| Scheduled jobs | all (`01` §Scheduled jobs) | price refresh and daily snapshot only; `record_recurring` and `backup` are off (the PC owns both) |
| Sync server (LAN listener) | when a phone is paired | never |
| Sync client | never | yes |
| Import page, backups, data-folder buttons | shown | hidden |

## Sync server (desktop, `app/services/sync/lan.py`)

A **second** uvicorn server in the same process, started by the lifespan only when the
`sync_enabled` setting is true. It binds `0.0.0.0:sync_port` (default **8766**) and mounts a
separate FastAPI app that serves **only** `/sync/v1/*`. The main app keeps binding `127.0.0.1`,
so nothing else becomes reachable from the network. Windows asks once to allow it through the
firewall; answer for private networks only.

Every request needs `Authorization: Bearer <token>`. Tokens are 32 random bytes (urlsafe base64),
issued at pairing and stored only as a SHA-256 hash in the `sync_devices` table. Wrong or missing
token → 401 and a log line; five failures from one IP in a minute → 429 for ten minutes.

| Endpoint | Does |
|---|---|
| `GET /sync/v1/hello` | `{app_version, schema_revision, server_name, device_id}` for the caller. |
| `POST /sync/v1/push` | Body `{ops: [OutboxOp]}`. Applies ops in order (below). Returns `{results: [OpResult]}`. |
| `GET /sync/v1/snapshot` | A consistent copy of the database (SQLite online backup to a temp file), streamed as `application/octet-stream`, with `X-Schema-Revision`. The copy's `sync_*` tables are emptied first, so pairing records never leave the PC. |

Pairing (main app, `127.0.0.1` only):

| Endpoint | Does |
|---|---|
| `GET /api/sync/status` | `{role, enabled, running, port, addresses: [LAN IPv4s], pc_name, devices: [{id, name, paired_at, last_seen_at, last_sync_at}]}` |
| `PUT /api/sync/enabled` | `{enabled, port?}`. Starts or stops the listener; the lifespan starts it again at every launch while `sync_enabled` is true. |
| `POST /api/sync/pair` | `{name}` → creates a device, returns `{device_id, token, pairing_uri}` once. The UI shows the URI as a QR code. The token is never retrievable again. |
| `DELETE /api/sync/devices/{id}` | Unpairs. |

`pairing_uri` = `passbook://pair?h=<ip1>,<ip2>&p=<port>&t=<token>&d=<device_id>&n=<pc name>`.

## Outbox (phone, `app/services/sync/outbox.py`)

A middleware, installed only when `role == phone`, records every **successful** (`2xx`)
`POST`/`PUT`/`PATCH`/`DELETE` under `/api/` into `sync_outbox`:

| Column | |
|---|---|
| `id` | PK |
| `op_id` | UUID4 string, unique; the PC uses it for idempotency |
| `created_at` | UTC |
| `method`, `path`, `query` | as sent |
| `body` | JSON text or null |
| `response` | the phone's JSON response (used to learn which new ids it created) |
| `summary` | plain-English label worked out before the request runs (`describe.py`), e.g. "Balance £850.00 for Joint current on 10 Sep 2026", shown in the sync report |

**Not recorded** (local-only or not meaningful on the PC): `/api/prices/refresh`, `/api/sync/*`,
`/api/settings/backup*`, `/api/system/*`, `/api/imports*`, and any non-JSON body. The list is
`OUTBOX_EXCLUDE` in one place.

While a sync is running, every mutating `/api/` request on the phone returns **423**
`{"error": {"code": "sync_in_progress", ...}}` so nothing is written into a database that is
about to be replaced.

### Ids created on the phone

A `before_insert` mapper event (phone role only, `app/services/sync/ids.py`) gives every new row
with a single integer `id` primary key the next value of **one counter shared by every table**,
starting at `PHONE_ID_BASE` (seeded from the highest phone id in any table when the app starts).
A per-table counter is not enough: a balance entry and an account would both get `2**40`, and the
PC's id map could swap one for the other. `sync_*` tables are local and keep ordinary ids. Rows
copied from the PC always have ids far below `2**40`, so **any integer ≥ `PHONE_ID_BASE` in a path
or body is a phone-made id** and nothing else (money and units are floats; `2**40` is ≈ 1.1 trillion and well inside
JavaScript's safe integer range).

## Applying a push (desktop, `app/services/sync/apply.py`)

For each op, in order:

1. If `op_id` is in `sync_applied_ops`, return the stored result (a retried push is harmless).
2. Rewrite ids: replace every phone id (≥ `PHONE_ID_BASE`) in the path segments and anywhere in
   the JSON body with the PC id it was mapped to earlier in this push. A phone id with no
   mapping means its create was rejected → reject this op with `depends_on_rejected`.
3. Dispatch the request to the main app in-process (ASGI, `httpx.ASGITransport`), with the same
   method, path, query and body. The normal routers, services, validation and snapshot rebuilds
   run exactly as if the user had clicked in the PC's UI.
4. On `2xx`: walk the phone's recorded response and the PC's response together; wherever the
   phone's has an integer ≥ `PHONE_ID_BASE`, map it to the PC's value at the same place.
   Status `applied`.
5. On `4xx`: status `rejected` with the PC's error message. **Later ops still run**; any that
   depend on the rejected one are rejected by step 2.
6. Record `(op_id, device_id, applied_at, status, message, id_map)` in `sync_applied_ops`.

A rejected op's message is the PC's own. The ledger re-checks every sale in date order, so its
message can name a different sale from the phone's; for those the PC leads with "There weren't
enough units left on the PC for this sale; they were sold there first." and keeps the ledger's
detail in brackets. The report shows each rejection under the phone's own change summary.

**Concurrent edits**: if the same thing was changed on the PC and on the phone between syncs,
the phone's change is applied last and so wins, and it is listed in the sync report. A change to
something the PC has since deleted is rejected (the PC returns 404) and listed as well.

## Sync client (phone, `app/services/sync/client.py`)

`sync_now()`, from the Sync button, and automatically when the app opens and every 15 minutes
while it is open and on Wi-Fi:

1. Read `sync.json` in the data folder: `{hosts, port, token, device_id, pc_name, last_sync_at,
   last_report}`. It lives **outside** the database because the database is replaced.
2. Try each host with `GET /hello` (2 s timeout). None answer → status `pc_unreachable`, stop
   quietly (this is the normal case away from home).
3. Refuse if the PC's `schema_revision` differs from the phone's: "Update Waymark on your
   phone/PC so both are on version X". No data is touched.
4. Take the sync lock (mutations now get 423).
5. `POST /push` with every outbox row, oldest first.
6. `GET /snapshot` into `networth.db.incoming`; check it opens and its `schema_revision` matches.
7. Dispose the SQLAlchemy engine, move `networth.db` to `networth.db.previous` (one kept),
   move the incoming file into place, delete `-wal`/`-shm`, reopen. The outbox is empty in the
   new copy because the PC never records one.
8. Save the report (`applied`, `rejected` with reasons, time) to `sync.json`, release the lock.

Any failure before step 7 leaves the phone's database and outbox untouched, so the next sync
simply tries again; the PC's idempotency makes re-sending safe.

All `/api/sync/*` endpoints answer 409 `wrong_role` when called on the other role.
`GET /api/health` includes `role`, which the UI uses to switch between the PC and phone views.

Phone API (main app on the phone): `GET /api/sync/client` (paired?, PC name, last sync, pending
change count, last report), `POST /api/sync/client/pair` (`{pairing_uri}`),
`POST /api/sync/client/sync` (runs `sync_now`, returns the report), `DELETE /api/sync/client`.

## Android shell (`android/`)

- Kotlin, one `AppCompatActivity` with a full-screen `WebView`, `minSdk 26`, `targetSdk 35`,
  application id `com.passbook.app` (from before the rename to Waymark; changing it would make
  every phone reinstall and re-pair), arm64 only. Version name and code come from
  `backend/app/__init__.py` (`0.1.2` → `102`), so every platform shares one version.
- **Chaquopy** embeds CPython 3.12. The build copies `backend/app` in as Python source and installs
  `android/app/requirements.txt`: the backend's dependencies minus yfinance/pandas, uvicorn's
  compiled extras and the desktop window. Compiled packages (numpy, pydantic-core, markupsafe)
  come from Chaquopy's Android repository, so they are left unpinned there.
- `backend/alembic`, `alembic.ini` and `frontend/dist` go in as assets and are unpacked to private
  storage once per installed version; `NW_RESOURCE_DIR` points the backend at them
  (`app/core/paths.py`).
- `app.mobile.start(data_dir, resource_dir)` sets `NW_ROLE=phone`, runs uvicorn (asyncio loop,
  h11) on a free `127.0.0.1` port in a background thread and returns the port; the WebView loads
  it. It is idempotent per process. The phone role skips the import routes (they need pandas).
- Prices: `app/providers/factory.default_provider()` gives `YahooHttpProvider` on the phone, which
  calls Yahoo's public chart and search endpoints with plain HTTPS (same `PriceProvider`
  protocol and normalisation), because yfinance's `curl_cffi` has no Android build.
- QR pairing uses the Google code scanner (no camera permission). The page calls
  `window.PassbookAndroid.scanQrCode()` and gets the text back through
  `window.onPassbookQrScanned` (`frontend/src/lib/android.ts`).
- Only `127.0.0.1` loads inside the app (cleartext allowed for it alone); other links open in the
  browser. `allowBackup` is off so the data never goes to Google's cloud backup. Data lives in the
  app's private storage and is removed on uninstall; because the PC is master, reinstalling only
  means pairing again.
- Background: no work runs while the app is closed. On open, the backend's existing `catch_up`
  fills in missed snapshot days and the client syncs.

## Distribution

- `.github/workflows/android.yml` builds a **debug APK** on every push that touches `android/`,
  `backend/` or `frontend/`, uploaded as a workflow artifact, for testing.
- The Release workflow gains an Android job: a **release APK** signed with a key held in the
  repository secrets (`ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`,
  `ANDROID_KEY_PASSWORD`), attached to the GitHub Release as `waymark-<version>.apk` next to the
  Windows installer and the `.deb`. The same key must sign every release or Android refuses the
  upgrade. The secrets are optional: without them the APK is signed with the build machine's
  debug key, so each release installs only after uninstalling the previous one and resyncing
  from the PC.
- Install by opening the release on the phone and allowing the browser to install unknown apps.
  Obtainium can follow the releases for automatic updates.

## Mobile layout (frontend)

Below the `md` breakpoint (768 px):

- The masthead's navigation becomes a slide-in drawer opened from a menu button in a sticky top
  bar; it closes on navigation. The household total sits in the drawer header.
- The top bar shows the menu button, the Waymark wordmark, the refresh icon (no label), Quick
  update as an icon button and the bell. "Search / Ctrl K" and "Add account" move into the drawer.
- Page padding 16 px. Grids collapse to one column. Tables scroll horizontally inside their card
  (never the page). Charts keep their full height and use fewer x ticks.
- Dialogs and sheets are full width.
- On the phone role, a **Sync** row in the drawer shows the PC name, last sync time, the count of
  changes waiting, and a "Sync now" button; the report of the last sync opens from it.

## Data model additions (migration `sync_tables`)

| Table | Columns |
|---|---|
| `sync_devices` *(desktop)* | `id` PK, `name`, `token_hash` unique, `paired_at`, `last_seen_at`, `last_sync_at`, `revoked_at` |
| `sync_applied_ops` *(desktop)* | `op_id` PK, `device_id` FK → `sync_devices` (cascade), `applied_at`, `status` (`applied`/`rejected`), `message`, `id_map` JSON |
| `sync_outbox` *(phone)* | as above |

Settings keys: `sync_enabled` (false), `sync_port` (8766).

## Dependencies

- Backend: `httpx` moves from the dev group to the main dependencies. The PC uses it to dispatch
  pushed ops into its own app in-process (`ASGITransport`) and the phone uses it to call the PC.
  It is already in the lock file (FastAPI's test client needs it), so nothing new is downloaded.
- Frontend: `qrcode` (generate the pairing QR on the PC; small, no dependencies).
- Android: Chaquopy Gradle plugin, AndroidX `webkit`, Google code scanner (`play-services-code-scanner`).

## Tests

- Outbox: a phone-role app records a balance entry POST, skips a price refresh, skips a 4xx.
- Phone ids: a new account made in phone role gets an id ≥ `2**40`; desktop role is unchanged.
- Apply: a push that creates an account and then a balance entry on it lands on the PC with the
  PC's own ids; re-sending the same push changes nothing; an op after a rejected create is
  rejected with `depends_on_rejected`; an impossible sell is rejected with the PC's message.
- Auth: no token → 401; revoked device → 401.
- Snapshot: the streamed file opens, has the PC's rows and an empty outbox.
- Client end-to-end (both apps in one test process, `httpx.ASGITransport`): make changes on the
  phone, sync, the PC has them, the phone's database equals the PC's and its outbox is empty.
