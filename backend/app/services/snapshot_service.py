"""docs/03-domain-logic.md §4 "Snapshots and history"."""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import today
from app.core.enums import SnapshotSource, ValuationMethod
from app.db import SessionLocal
from app.engine import ledger
from app.models.accounts import Account
from app.models.instruments import Instrument
from app.models.snapshots import AccountSnapshot
from app.models.transactions import Transaction
from app.providers.base import PriceProvider
from app.services import ledger_service, price_service, valuation_service

logger = logging.getLogger("app.snapshot_service")


# ---------------------------------------------------------------------------
# Writing snapshots
# ---------------------------------------------------------------------------


def _has_data(db: Session, account: Account) -> bool:
    if account.valuation_method == ValuationMethod.holdings:
        return (
            db.scalar(
                select(Transaction.id).where(Transaction.account_id == account.id).limit(1)
            )
            is not None
        )
    if account.valuation_method == ValuationMethod.defined_benefit:
        return account.db_pension_details is not None
    # A loan is valued from its terms alone, so it can have data with no balance entry at all.
    if account.valuation_method == ValuationMethod.amortising and account.loan_details is not None:
        return True
    if account.valuation_method in (
        ValuationMethod.balance,
        ValuationMethod.model,
        ValuationMethod.amortising,
    ):
        return valuation_service.latest_balance_entry(db, account.id, today()) is not None
    return False


def _write_snapshot(db: Session, account: Account, on: date, source: SnapshotSource) -> None:
    valuation = valuation_service.value_account(
        db, account, on, live=(on == today()), with_net_contributions=True
    )
    row = db.get(AccountSnapshot, (account.id, on))
    if row is None:
        row = AccountSnapshot(account_id=account.id, date=on)
        db.add(row)
    row.value_gbp = valuation.value_gbp
    row.cost_basis_gbp = valuation.cost_basis_gbp
    row.net_contributions_gbp = valuation.net_contributions_gbp
    row.is_estimated = valuation.is_estimated
    row.source = source


def take(db: Session, on: date) -> None:
    """Snapshot every non-archived account that has any data, dated `on`."""
    accounts = list(db.scalars(select(Account).where(Account.is_archived.is_(False))).all())
    for account in accounts:
        if not _has_data(db, account):
            continue
        _write_snapshot(db, account, on, SnapshotSource.daily)
    db.commit()


def revalue_today(db: Session) -> None:
    """Rewrite today's existing snapshot rows at the current live values.

    Today's row is often written at startup (catch_up) from quotes cached days ago; without
    this it keeps them until the 22:15 job, or for good if the app is closed first (#28).
    Only rows that already exist are touched: creating today's row for every account would
    make a refresh that races startup look to catch_up as if the missing days were done.
    """
    on = today()
    account_ids = set(db.scalars(select(AccountSnapshot.account_id).where(AccountSnapshot.date == on)).all())
    if not account_ids:
        return
    accounts = db.scalars(
        select(Account).where(Account.id.in_(account_ids), Account.is_archived.is_(False))
    ).all()
    for account in accounts:
        _write_snapshot(db, account, on, SnapshotSource.daily)
    db.commit()


def refresh_quotes(db: Session, provider: PriceProvider, force: bool = False) -> price_service.RefreshResult:
    """price_service.refresh_quotes, then carry any new quotes into today's snapshot."""
    result = price_service.refresh_quotes(db, provider, force=force)
    if result.refreshed:
        revalue_today(db)
    return result


def _all_dates_in_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _backfill_holdings_account(
    db: Session,
    account: Account,
    dates: list[date],
    source: SnapshotSource = SnapshotSource.backfill,
) -> None:
    """docs/03-domain-logic.md §4: replay once per account rather than per day.

    Every date is valued offline (`live=False`), so callers keep today out of `dates` when it
    should use the live positions cache.
    """
    rows = ledger_service.confirmed_txns(db, account.id)
    txns = [ledger_service.to_engine_txn(r) for r in rows]
    states = ledger.replay_series(txns, dates, strict=False)

    instrument_ids = {iid for state in states for iid in state.held()}
    instruments = (
        {
            i.id: i
            for i in db.scalars(select(Instrument).where(Instrument.id.in_(instrument_ids))).all()
        }
        if instrument_ids
        else {}
    )

    sign = -1.0 if account.category in valuation_service.LIABILITY_CATEGORIES else 1.0
    for on, state in zip(dates, states, strict=True):
        total = state.cash_gbp
        cost_basis = 0.0
        is_estimated = False
        for instrument_id, pos in state.held().items():
            instrument = instruments.get(instrument_id)
            if instrument is None:
                continue
            result = price_service.price_gbp(db, instrument, on, live=False)
            total += pos.units * result.price_gbp
            cost_basis += pos.cost_gbp
            if result.is_stale:
                is_estimated = True

        row = db.get(AccountSnapshot, (account.id, on))
        if row is None:
            row = AccountSnapshot(account_id=account.id, date=on)
            db.add(row)
        row.value_gbp = round(total * sign, 2)
        row.cost_basis_gbp = round(cost_basis, 2)
        row.net_contributions_gbp = round(state.net_contributions_gbp, 2)
        row.is_estimated = is_estimated
        row.source = source


def catch_up(db: Session, provider: PriceProvider | None = None) -> None:
    """Startup: fill missing snapshot days, backfilling price history where possible."""
    on_today = today()
    # Catch up from the stalest account, not the newest snapshot overall: one account edited or
    # added today has a row for today while the rest may still be days behind.
    latest_by_account = db.execute(
        select(AccountSnapshot.account_id, func.max(AccountSnapshot.date))
        .join(Account, Account.id == AccountSnapshot.account_id)
        .where(Account.is_archived.is_(False))
        .group_by(AccountSnapshot.account_id)
    ).all()
    if not latest_by_account:
        take(db, on_today)
        return
    last = min(latest for _account_id, latest in latest_by_account)
    if last >= on_today:
        return

    missing_start = last + timedelta(days=1)
    missing_end = on_today - timedelta(days=1)
    accounts = [
        a
        for a in db.scalars(select(Account).where(Account.is_archived.is_(False))).all()
        if _has_data(db, a)
    ]

    if missing_start <= missing_end:
        holdings_accounts = [a for a in accounts if a.valuation_method == ValuationMethod.holdings]
        if provider is not None and holdings_accounts:
            instrument_ids = list(
                db.scalars(
                    select(Transaction.instrument_id)
                    .where(
                        Transaction.account_id.in_([a.id for a in holdings_accounts]),
                        Transaction.instrument_id.isnot(None),
                    )
                    .distinct()
                ).all()
            )
            if instrument_ids:
                price_service.ensure_history(db, provider, instrument_ids, missing_start, missing_end)

        dates = _all_dates_in_range(missing_start, missing_end)
        for account in accounts:
            if account.valuation_method == ValuationMethod.holdings:
                _backfill_holdings_account(db, account, dates)
            else:
                for on in dates:
                    _write_snapshot(db, account, on, SnapshotSource.backfill)
        db.commit()

    take(db, on_today)


def first_data_date(db: Session, account: Account) -> date | None:
    """The first day this account had any value at all — its earliest transaction, balance entry
    or (for a loan) drawdown. Returns None when that can't be determined."""
    if account.valuation_method == ValuationMethod.holdings:
        return db.scalar(
            select(func.min(Transaction.date)).where(Transaction.account_id == account.id)
        )
    candidates: list[date] = []
    earliest = valuation_service.earliest_balance_entry(db, account.id)
    if earliest is not None:
        candidates.append(earliest.date)
    if account.valuation_method == ValuationMethod.defined_benefit and account.db_pension_details:
        candidates.append(account.db_pension_details.accrued_as_of)
    if account.valuation_method == ValuationMethod.amortising:
        loan = account.loan_details
        if loan is not None and loan.start_date is not None:
            candidates.append(loan.start_date)
    return min(candidates) if candidates else None


def rebuild(db: Session, account_id: int, from_date: date) -> None:
    """Delete and recompute one account's snapshots from `from_date` to today.

    Days before the account's first data are dropped rather than recomputed: `catch_up` backfills
    every account over the whole snapshot range, so an account added later carries a run of
    zero-valued rows before it existed, which plot as a flat £0 line reaching back to whenever the
    household's history starts.
    """
    account = db.get(Account, account_id)
    if account is None:
        return
    on_today = today()
    first = first_data_date(db, account)
    db.query(AccountSnapshot).filter(
        AccountSnapshot.account_id == account_id, AccountSnapshot.date >= from_date
    ).delete(synchronize_session=False)
    if first is not None:
        db.query(AccountSnapshot).filter(
            AccountSnapshot.account_id == account_id, AccountSnapshot.date < first
        ).delete(synchronize_session=False)
    start = max(from_date, first) if first is not None else from_date
    dates = _all_dates_in_range(start, on_today)
    if account.valuation_method == ValuationMethod.holdings:
        # docs/03-domain-logic.md §4: replay the ledger once for the whole range rather than once
        # per day. Valuing each day on its own is O(days x transactions), which on a pension with
        # years of history is minutes of CPU for a single import.
        past = [d for d in dates if d < on_today]
        if past:
            _backfill_holdings_account(db, account, past, SnapshotSource.rebuild)
        if dates and dates[-1] == on_today:
            # Today keeps the live path: positions cache, account cash and live quotes.
            _write_snapshot(db, account, on_today, SnapshotSource.rebuild)
    else:
        for on in dates:
            _write_snapshot(db, account, on, SnapshotSource.rebuild)
    db.commit()


# ---------------------------------------------------------------------------
# Coalescing background rebuild — docs/03-domain-logic.md §4 "rebuild(...)":
# "Coalesce requests per account (keep the earliest from_date)."
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_pending: dict[int, date] = {}
_in_progress: set[int] = set()


def _rebuild_worker(account_id: int) -> None:
    while True:
        with _lock:
            from_date = _pending.pop(account_id, None)
            if from_date is None:
                _in_progress.discard(account_id)
                return
        try:
            with SessionLocal() as db:
                rebuild(db, account_id, from_date)
        except Exception:
            logger.exception("Snapshot rebuild failed for account %s", account_id)


def request_rebuild(account_id: int, from_date: date) -> None:
    """Call from any create/update/delete of a balance entry, transaction, or growth model."""
    with _lock:
        current = _pending.get(account_id)
        if current is None or from_date < current:
            _pending[account_id] = from_date
        if account_id in _in_progress:
            return
        _in_progress.add(account_id)
    threading.Thread(target=_rebuild_worker, args=(account_id,), daemon=True).start()


# ---------------------------------------------------------------------------
# Rebuild-all job (POST /snapshots/rebuild + GET /jobs/{id})
# ---------------------------------------------------------------------------


@dataclass
class JobStatus:
    status: str = "pending"  # pending | running | done | error
    progress: float = 0.0
    error: str | None = None


_jobs: dict[str, JobStatus] = {}
_jobs_lock = threading.Lock()


def _run_rebuild_job(job_id: str, account_id: int | None, from_date: date) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        with SessionLocal() as db:
            if account_id is not None:
                rebuild(db, account_id, from_date)
                with _jobs_lock:
                    _jobs[job_id].progress = 1.0
            else:
                account_ids = list(
                    db.scalars(select(Account.id).where(Account.is_archived.is_(False))).all()
                )
                for i, aid in enumerate(account_ids):
                    rebuild(db, aid, from_date)
                    with _jobs_lock:
                        _jobs[job_id].progress = (i + 1) / max(len(account_ids), 1)
        with _jobs_lock:
            _jobs[job_id].status = "done"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Rebuild job %s failed", job_id)
        with _jobs_lock:
            _jobs[job_id].status = "error"
            _jobs[job_id].error = str(exc)


def start_rebuild_job(account_id: int | None, from_date: date) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = JobStatus()
    threading.Thread(target=_run_rebuild_job, args=(job_id, account_id, from_date), daemon=True).start()
    return job_id


def get_job(job_id: str) -> JobStatus | None:
    with _jobs_lock:
        return _jobs.get(job_id)


# ---------------------------------------------------------------------------
# Reading — history and changes
# ---------------------------------------------------------------------------


@dataclass
class HistorySeries:
    key: str
    label: str
    values: list[float]


@dataclass
class HistoryResult:
    dates: list[date]
    total: list[float]
    series: list[HistorySeries]


def _period_key(on: date, granularity: str) -> tuple:
    if granularity == "week":
        iso = on.isocalendar()
        return (iso[0], iso[1])
    if granularity == "month":
        return (on.year, on.month)
    return (on.year, on.month, on.day)


def _last_date_per_period(dates: list[date], granularity: str) -> list[date]:
    if granularity == "day":
        return dates
    last_by_period: dict[tuple, date] = {}
    for d in dates:
        last_by_period[_period_key(d, granularity)] = d
    return sorted(last_by_period.values())


def _scoped_accounts(db: Session, person_id: int | None) -> tuple[list[Account], set[int]]:
    from app.models.people import Person
    from app.services import account_service

    accounts = [
        a for a in account_service.list_accounts(db, include_archived=False) if a.include_in_networth
    ]
    if person_id is not None:
        scope_ids = {person_id}
    else:
        people = list(db.scalars(select(Person).where(Person.is_archived.is_(False))).all())
        scope_ids = {p.id for p in people if p.include_in_household}
    return accounts, scope_ids


@dataclass(frozen=True)
class _Point:
    account_id: int
    date: date
    value_gbp: float


def _forward_fill(rows: list[AccountSnapshot]) -> list[_Point]:
    """Carry each account's last value onto later dates where it has no snapshot.

    Snapshots for one day are written at different times (the nightly job, rebuilds after an
    edit), so a date can have rows for only some accounts, e.g. a new account added this morning
    before tonight's snapshot of the rest. Summing that date as-is would count every other
    account as £0 and plunge the total.
    """
    dates = sorted({r.date for r in rows})
    by_account: dict[int, dict[date, float]] = {}
    for r in rows:
        by_account.setdefault(r.account_id, {})[r.date] = r.value_gbp
    out: list[_Point] = []
    for account_id, values in by_account.items():
        first = min(values)
        last: float | None = None
        for d in dates:
            if d < first:
                continue
            last = values.get(d, last)
            if last is not None:
                out.append(_Point(account_id, d, last))
    return out


def _with_live_today(
    db: Session, accounts: list[Account], rows: list[_Point], on_today: date
) -> list[_Point]:
    """Add a provisional point for today for every account that has no snapshot for it yet.

    Today's rows are only written by the 22:15 job or by `catch_up` at startup, so an app left
    running would otherwise plot a chart that stops at yesterday all day, even with prices and
    balances refreshed. Valuing live here is cheap and offline: `price_gbp(live=True)` reads the
    cached quote off the instrument row and never hits the network, so this stays safe in a GET.

    Every data-bearing account gets a point, not just the ones that moved: a date holding only
    some accounts sums as if the rest were £0. Accounts with no data left to value are carried
    forward at their last known figure for the same reason.
    """
    have_today = {p.account_id for p in rows if p.date == on_today}
    # `_forward_fill` emits each account's points in date order, so the last write per account
    # is its latest value.
    last_known = {p.account_id: p.value_gbp for p in rows}

    out = list(rows)
    for account in accounts:
        if account.id in have_today:
            continue
        if _has_data(db, account):
            valuation = valuation_service.value_account(db, account, on_today, live=True)
            out.append(_Point(account.id, on_today, valuation.value_gbp))
        elif account.id in last_known:
            out.append(_Point(account.id, on_today, last_known[account.id]))
    return out


def history(
    db: Session,
    person_id: int | None,
    date_from: date,
    date_to: date,
    granularity: str = "day",
    group_by: str = "category",
) -> HistoryResult:
    accounts, scope_ids = _scoped_accounts(db, person_id)
    account_by_id = {a.id: a for a in accounts}
    if not account_by_id:
        return HistoryResult(dates=[], total=[], series=[])

    rows = list(
        db.scalars(
            select(AccountSnapshot).where(
                AccountSnapshot.account_id.in_(account_by_id.keys()),
                AccountSnapshot.date >= date_from,
                AccountSnapshot.date <= date_to,
            )
        ).all()
    )
    rows = _forward_fill(rows)

    on_today = today()
    if date_from <= on_today <= date_to:
        rows = _with_live_today(db, accounts, rows, on_today)

    per_date: dict[date, dict[str, float]] = {}
    labels: dict[str, str] = {}
    for row in rows:
        account = account_by_id.get(row.account_id)
        if account is None:
            continue
        if group_by == "person":
            for owner in account.owners:
                if owner.person_id not in scope_ids:
                    continue
                key = str(owner.person_id)
                labels[key] = owner.person.name
                bucket = per_date.setdefault(row.date, {})
                bucket[key] = bucket.get(key, 0.0) + row.value_gbp * owner.share
            continue

        share = sum(o.share for o in account.owners if o.person_id in scope_ids)
        if share <= 0:
            continue
        if group_by == "account":
            key, label = str(account.id), account.name
        else:
            key, label = account.category.value, account.category.value
        labels[key] = label
        bucket = per_date.setdefault(row.date, {})
        bucket[key] = bucket.get(key, 0.0) + row.value_gbp * share

    all_dates = sorted(per_date.keys())
    dates = _last_date_per_period(all_dates, granularity)
    keys = sorted(labels.keys())

    series = [
        HistorySeries(
            key=key,
            label=labels[key],
            values=[round(per_date.get(d, {}).get(key, 0.0), 2) for d in dates],
        )
        for key in keys
    ]
    total = [round(sum(per_date.get(d, {}).values()), 2) for d in dates]
    return HistoryResult(dates=dates, total=total, series=series)


def account_history(
    db: Session, account_id: int, date_from: date, date_to: date
) -> list[AccountSnapshot]:
    return list(
        db.scalars(
            select(AccountSnapshot)
            .where(
                AccountSnapshot.account_id == account_id,
                AccountSnapshot.date >= date_from,
                AccountSnapshot.date <= date_to,
            )
            .order_by(AccountSnapshot.date)
        ).all()
    )


def total_on_or_before(db: Session, scope_ids: set[int], on: date) -> float | None:
    """docs/03-domain-logic.md §4 "Changes": total on the nearest snapshot on or before `on`,
    taken independently per account so accounts opened at different times don't block each other."""
    from app.services import account_service

    accounts = [
        a for a in account_service.list_accounts(db, include_archived=False) if a.include_in_networth
    ]
    total = 0.0
    found = False
    for account in accounts:
        share = sum(o.share for o in account.owners if o.person_id in scope_ids)
        if share <= 0:
            continue
        row = db.scalars(
            select(AccountSnapshot)
            .where(AccountSnapshot.account_id == account.id, AccountSnapshot.date <= on)
            .order_by(AccountSnapshot.date.desc())
            .limit(1)
        ).first()
        if row is not None:
            total += row.value_gbp * share
            found = True
    return round(total, 2) if found else None
