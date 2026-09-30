"""Orchestrates the Phase 8 pipeline described in docs/06-imports-future.md: upload -> profile ->
parse -> instrument matching -> dedupe -> preview/reconciliation -> commit -> rebuild -> rollback.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.clock import now_utc_naive, today
from app.core.enums import (
    BalanceSource,
    ContributionSource,
    ImportKind,
    ImportStatus,
    TxnSource,
    TxnStatus,
    TxnType,
)
from app.core.errors import DomainError, NotFoundError
from app.db import SessionLocal
from app.engine import ledger
from app.models.accounts import Account
from app.models.imports import ImportBatch, ImportProfile
from app.models.positions import Position
from app.models.transactions import Transaction
from app.providers.base import PriceProvider
from app.services import account_service, ledger_service, price_service, snapshot_service
from app.services.importers import matching
from app.services.importers.bank import (
    BankRow,
    compute_daily_balances,
    has_running_balance_column,
    parse_bank_dataframe,
)
from app.services.importers.canonical import (
    CANONICAL_BALANCE_COLUMNS,
    CANONICAL_TXN_COLUMNS,
    CanonicalRow,
    RowError,
    header_signature,
    parse_canonical_dataframe,
)
from app.services.importers.mapping import apply_mapping

logger = logging.getLogger("app.importers")

_STAND_IN_TYPES = [TxnType.OPENING_BALANCE, TxnType.ADJUSTMENT]
_STAND_IN_SOURCES = [TxnSource.opening, TxnSource.manual]


def _imports_dir(batch_id: int) -> Path:
    d = Path(settings.data_dir) / "imports" / str(batch_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_batch(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise NotFoundError(f"Import batch {batch_id} not found")
    return batch


def list_batches(db: Session) -> list[ImportBatch]:
    return list(db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc())).all())


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def upload(
    db: Session, kind: ImportKind, account_id: int, filename: str, content: bytes
) -> tuple[ImportBatch, list[str], list[dict], str | None]:
    account_service.get_account(db, account_id)

    batch = ImportBatch(
        kind=kind, account_id=account_id, filename=filename, file_path="", status=ImportStatus.pending
    )
    db.add(batch)
    db.flush()

    target_dir = _imports_dir(batch.id)
    file_path = target_dir / filename
    file_path.write_bytes(content)
    batch.file_path = str(file_path)

    raw = pd.read_csv(file_path, dtype=str, keep_default_na=True)
    headers = [str(h) for h in raw.columns]
    batch.header_signature = header_signature(headers)

    matched_profile: ImportProfile | None = db.scalars(
        select(ImportProfile).where(
            ImportProfile.kind == kind, ImportProfile.header_signature == batch.header_signature
        )
    ).first()
    if matched_profile is not None:
        batch.profile_name = matched_profile.name
        batch.mapping_json = matched_profile.mapping_json

    sample = raw.head(20).where(pd.notna(raw.head(20)), None)
    sample_rows = sample.to_dict(orient="records")

    db.commit()
    db.refresh(batch)
    return batch, headers, sample_rows, (matched_profile.name if matched_profile else None)


def resolve_instruments(db: Session, batch: ImportBatch, resolutions: list[tuple[str, int]]) -> None:
    """Save the user's key -> instrument_id picks as aliases for this profile so the same
    profile never has to ask again (docs/06-imports-future.md step 4)."""
    for key, instrument_id in resolutions:
        symbol, isin, name = (key.split("|", 2) + ["", "", ""])[:3]
        alias = symbol or isin or name
        if alias:
            matching.save_alias(db, batch.profile_name, alias, instrument_id)
    db.commit()


def save_mapping(db: Session, batch: ImportBatch, profile_name: str, mapping: dict, save_as_profile: bool) -> ImportBatch:
    batch.profile_name = profile_name
    batch.mapping_json = json.dumps(mapping)
    if save_as_profile and batch.header_signature is not None:
        profile = db.scalars(select(ImportProfile).where(ImportProfile.name == profile_name)).first()
        if profile is None:
            profile = ImportProfile(
                name=profile_name,
                kind=batch.kind,
                mapping_json=batch.mapping_json,
                header_signature=batch.header_signature,
            )
            db.add(profile)
        else:
            profile.mapping_json = batch.mapping_json
            profile.header_signature = batch.header_signature
    db.commit()
    db.refresh(batch)
    return batch


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _canonical_dataframe(batch: ImportBatch) -> pd.DataFrame:
    raw = pd.read_csv(Path(batch.file_path), dtype=str, keep_default_na=True)
    canonical_columns = CANONICAL_TXN_COLUMNS if batch.kind == ImportKind.transactions else CANONICAL_BALANCE_COLUMNS

    if batch.mapping_json:
        mapping = json.loads(batch.mapping_json)
        return apply_mapping(raw, mapping, canonical_columns)

    renamed = raw.rename(columns={h: h.strip().lower() for h in raw.columns})
    out = pd.DataFrame(index=renamed.index)
    for col in canonical_columns:
        out[col] = renamed[col] if col in renamed.columns else None
    return out


def _parse_transactions(batch: ImportBatch) -> tuple[list[CanonicalRow], list[RowError]]:
    return parse_canonical_dataframe(_canonical_dataframe(batch))


def _parse_bank(batch: ImportBatch) -> tuple[list[BankRow], list[RowError]]:
    return parse_bank_dataframe(_canonical_dataframe(batch))


def _existing_external_ids(db: Session, account_id: int) -> set[str]:
    return set(
        db.scalars(
            select(Transaction.external_id).where(
                Transaction.account_id == account_id, Transaction.external_id.isnot(None)
            )
        ).all()
    )


def _dedupe(rows: list[CanonicalRow], existing_ids: set[str]) -> tuple[list[CanonicalRow], int]:
    seen: set[str] = set()
    kept: list[CanonicalRow] = []
    skipped = 0
    for row in rows:
        key = row.external_id or row.dedupe_hash()
        if key in existing_ids or key in seen:
            skipped += 1
            continue
        seen.add(key)
        kept.append(row)
    return kept, skipped


def _stand_in_rows(
    db: Session, account_id: int, instrument_ids: set[int], include_cash: bool
) -> list[Transaction]:
    conditions = [
        Transaction.account_id == account_id,
        Transaction.type.in_(_STAND_IN_TYPES),
        Transaction.source.in_(_STAND_IN_SOURCES),
    ]
    id_conditions = []
    if instrument_ids:
        id_conditions.append(Transaction.instrument_id.in_(instrument_ids))
    if include_cash:
        id_conditions.append(Transaction.instrument_id.is_(None))
    if not id_conditions:
        return []
    return list(db.scalars(select(Transaction).where(*conditions, or_(*id_conditions))).all())


def _row_to_txn_kwargs(row: CanonicalRow, instrument_id: int | None) -> dict:
    cost_basis_gbp = 0.0
    if row.type in {"OPENING_BALANCE", "TRANSFER_IN", "ADJUSTMENT"}:
        if row.price is not None:
            cost_basis_gbp = round(row.units * row.price * row.fx_gbp_per_unit, 2)
        else:
            cost_basis_gbp = round(abs(row.amount_gbp), 2)
    return {
        "date": row.date,
        "type": TxnType(row.type),
        "instrument_id": instrument_id,
        "units": round(row.units, 8),
        "price_native": row.price,
        "currency": row.currency,
        "fx_gbp_per_unit": row.fx_gbp_per_unit,
        "amount_gbp": round(row.amount_gbp, 2),
        "fees_gbp": round(row.fees_gbp, 2),
        "cost_basis_gbp": cost_basis_gbp,
        "contribution_source": ContributionSource(row.contribution_source) if row.contribution_source else None,
        "notes": row.notes,
        "external_id": row.external_id or row.dedupe_hash(),
    }


@dataclass
class _PreparedImport:
    kept_rows: list[CanonicalRow]
    row_errors: list[RowError]
    rows_total: int
    dedupe_skipped: int
    matched: dict[str, int]
    unmatched: list[matching.UnmatchedKey]
    instrument_ids: set[int] = field(default_factory=set)
    needs_cash_stand_in: bool = False


def _prepare_transactions_import(
    db: Session, batch: ImportBatch, provider: PriceProvider | None
) -> _PreparedImport:
    rows, errors = _parse_transactions(batch)
    existing_ids = _existing_external_ids(db, batch.account_id)
    kept, dedupe_skipped = _dedupe(rows, existing_ids)
    matched, unmatched = matching.match_instruments(db, batch.profile_name, kept, provider)
    instrument_ids = {iid for iid in matched.values()}
    needs_cash_stand_in = any(r.instrument_key() is None and abs(r.amount_gbp) > 0.005 for r in kept)
    return _PreparedImport(
        kept_rows=kept,
        row_errors=errors,
        rows_total=len(rows) + len(errors),
        dedupe_skipped=dedupe_skipped,
        matched=matched,
        unmatched=unmatched,
        instrument_ids=instrument_ids,
        needs_cash_stand_in=needs_cash_stand_in,
    )


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationRow:
    instrument_id: int | None
    symbol: str | None
    name: str | None
    current_units: float
    current_avg_cost_gbp: float
    imported_units: float
    imported_avg_cost_gbp: float
    units_diff: float
    avg_cost_diff_gbp: float


@dataclass
class PreviewResult:
    counts_by_type: dict[str, int]
    date_from: date | None
    date_to: date | None
    row_errors: list[RowError]
    ledger_warnings: list[str]
    reconciliation: list[ReconciliationRow]
    unmatched_instruments: list[matching.UnmatchedKey]
    cash_diff_gbp: float | None
    ready: bool


def preview_transactions(
    db: Session, batch: ImportBatch, provider: PriceProvider | None
) -> PreviewResult:
    prepared = _prepare_transactions_import(db, batch, provider)
    account = account_service.get_account(db, batch.account_id)

    existing = ledger_service.confirmed_txns(db, batch.account_id)
    stand_ins = _stand_in_rows(db, batch.account_id, prepared.instrument_ids, prepared.needs_cash_stand_in)
    stand_in_ids = {r.id for r in stand_ins}
    kept_existing = [r for r in existing if r.id not in stand_in_ids]

    new_txns = [
        ledger.Txn(**_txn_engine_kwargs(row, prepared.matched.get(row.instrument_key())), id=-(i + 1))
        for i, row in enumerate(prepared.kept_rows)
        if row.instrument_key() is None or row.instrument_key() in prepared.matched
    ]
    combined_state = ledger.replay(
        [ledger_service.to_engine_txn(r) for r in kept_existing] + new_txns, strict=False
    )

    current_positions = {p.instrument_id: p for p in db.scalars(
        select(Position).where(Position.account_id == batch.account_id)
    ).all()}

    instrument_ids = set(current_positions.keys()) | set(combined_state.held().keys())
    from app.models.instruments import Instrument

    instruments = {
        i.id: i for i in db.scalars(select(Instrument).where(Instrument.id.in_(instrument_ids))).all()
    } if instrument_ids else {}

    reconciliation = []
    for iid in sorted(instrument_ids):
        cur_pos = current_positions.get(iid)
        cur_units = cur_pos.units if cur_pos else 0.0
        cur_avg = cur_pos.cost_basis_gbp / cur_units if cur_pos and cur_units > 1e-9 else 0.0
        new_pos = combined_state.positions.get(iid)
        new_units = new_pos.units if new_pos else 0.0
        new_avg = new_pos.avg_cost_gbp if new_pos else 0.0
        instrument = instruments.get(iid)
        reconciliation.append(
            ReconciliationRow(
                instrument_id=iid,
                symbol=instrument.symbol if instrument else None,
                name=instrument.name if instrument else None,
                current_units=round(cur_units, 8),
                current_avg_cost_gbp=round(cur_avg, 2),
                imported_units=round(new_units, 8),
                imported_avg_cost_gbp=round(new_avg, 2),
                units_diff=round(new_units - cur_units, 8),
                avg_cost_diff_gbp=round(new_avg - cur_avg, 2),
            )
        )

    counts_by_type = dict(Counter(r.type for r in prepared.kept_rows))
    dates = [r.date for r in prepared.kept_rows]
    cash_diff = round(combined_state.cash_gbp - account.cash_balance_gbp, 2) if new_txns else None

    ready = not prepared.unmatched

    batch.rows_total = prepared.rows_total
    batch.rows_imported = len(new_txns)
    batch.rows_skipped = prepared.rows_total - len(new_txns)
    batch.row_errors_json = json.dumps([{"row": e.row, "message": e.message} for e in prepared.row_errors])
    batch.earliest_date = min(dates) if dates else None
    batch.status = ImportStatus.previewed
    db.commit()

    return PreviewResult(
        counts_by_type=counts_by_type,
        date_from=min(dates) if dates else None,
        date_to=max(dates) if dates else None,
        row_errors=prepared.row_errors,
        ledger_warnings=combined_state.warnings,
        reconciliation=reconciliation,
        unmatched_instruments=prepared.unmatched,
        cash_diff_gbp=cash_diff,
        ready=ready,
    )


def pending_rows(db: Session, batch: ImportBatch) -> list[CanonicalRow]:
    """The rows committing `batch` would write: parsed and deduped against the account."""
    rows, _errors = _parse_transactions(batch)
    kept, _skipped = _dedupe(rows, _existing_external_ids(db, batch.account_id))
    return kept


def new_ledger_warnings(db: Session, batch: ImportBatch, provider: PriceProvider | None) -> list[str]:
    """Ledger warnings (e.g. an oversell) that committing this batch *as is* would add on top of
    the account's current ones: no stand-ins replaced. Used by the Trading 212 sync to decide
    whether an incremental batch can commit without the user looking at it."""
    prepared = _prepare_transactions_import(db, batch, provider)
    existing = [ledger_service.to_engine_txn(r) for r in ledger_service.confirmed_txns(db, batch.account_id)]
    new_txns = [
        ledger.Txn(**_txn_engine_kwargs(row, prepared.matched.get(row.instrument_key())), id=10**12 + i)
        for i, row in enumerate(prepared.kept_rows)
        if row.instrument_key() is None or row.instrument_key() in prepared.matched
    ]
    before = ledger.replay(existing, strict=False).warnings
    after = ledger.replay(existing + new_txns, strict=False).warnings
    return after[len(before):] if len(after) > len(before) else []


def _txn_engine_kwargs(row: CanonicalRow, instrument_id: int | None) -> dict:
    kwargs = _row_to_txn_kwargs(row, instrument_id)
    return {
        "date": kwargs["date"],
        "type": kwargs["type"].value,
        "instrument_id": kwargs["instrument_id"],
        "units": kwargs["units"],
        "amount_gbp": kwargs["amount_gbp"],
        "cost_basis_gbp": kwargs["cost_basis_gbp"],
        "split_ratio": None,
    }


def preview_balances(
    db: Session, batch: ImportBatch, anchor_balance_gbp: float | None, anchor_date: date | None
) -> PreviewResult:
    rows, errors = _parse_bank(batch)
    account = account_service.get_account(db, batch.account_id)

    if not has_running_balance_column(rows) and (anchor_balance_gbp is None or anchor_date is None):
        batch.row_errors_json = json.dumps([{"row": e.row, "message": e.message} for e in errors])
        db.commit()
        return PreviewResult(
            counts_by_type={},
            date_from=min((r.date for r in rows), default=None),
            date_to=max((r.date for r in rows), default=None),
            row_errors=errors,
            ledger_warnings=[],
            reconciliation=[],
            unmatched_instruments=[],
            cash_diff_gbp=None,
            ready=False,
        )

    balances = compute_daily_balances(rows, anchor_balance_gbp, anchor_date)
    dates = sorted(balances.keys())
    from app.services import valuation_service

    latest_entry = valuation_service.latest_balance_entry(db, batch.account_id, today())
    current_balance = latest_entry.balance_gbp if latest_entry else 0.0
    imported_latest = balances[dates[-1]] if dates else current_balance

    reconciliation = [
        ReconciliationRow(
            instrument_id=None,
            symbol=None,
            name=account.name,
            current_units=0.0,
            current_avg_cost_gbp=current_balance,
            imported_units=0.0,
            imported_avg_cost_gbp=imported_latest,
            units_diff=0.0,
            avg_cost_diff_gbp=round(imported_latest - current_balance, 2),
        )
    ]

    batch.rows_total = len(rows) + len(errors)
    batch.rows_imported = len(dates)
    batch.rows_skipped = len(rows) + len(errors) - len(dates)
    batch.row_errors_json = json.dumps([{"row": e.row, "message": e.message} for e in errors])
    batch.earliest_date = dates[0] if dates else None
    batch.status = ImportStatus.previewed
    db.commit()

    return PreviewResult(
        counts_by_type={"BALANCE": len(dates)},
        date_from=dates[0] if dates else None,
        date_to=dates[-1] if dates else None,
        row_errors=errors,
        ledger_warnings=[],
        reconciliation=reconciliation,
        unmatched_instruments=[],
        cash_diff_gbp=None,
        ready=bool(dates),
    )


def preview(
    db: Session,
    batch: ImportBatch,
    provider: PriceProvider | None,
    anchor_balance_gbp: float | None = None,
    anchor_date: date | None = None,
) -> PreviewResult:
    if batch.kind == ImportKind.transactions:
        return preview_transactions(db, batch, provider)
    return preview_balances(db, batch, anchor_balance_gbp, anchor_date)


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------


def _serialise_txn(row: Transaction) -> dict:
    return {
        "account_id": row.account_id,
        "instrument_id": row.instrument_id,
        "date": row.date.isoformat(),
        "type": row.type.value,
        "units": row.units,
        "price_native": row.price_native,
        "currency": row.currency,
        "fx_gbp_per_unit": row.fx_gbp_per_unit,
        "amount_gbp": row.amount_gbp,
        "fees_gbp": row.fees_gbp,
        "cost_basis_gbp": row.cost_basis_gbp,
        "split_ratio": row.split_ratio,
        "contribution_source": row.contribution_source.value if row.contribution_source else None,
        "status": row.status.value,
        "source": row.source.value,
        "notes": row.notes,
    }


def commit_transactions(
    db: Session,
    batch: ImportBatch,
    provider: PriceProvider | None,
    replace_stand_ins: bool,
    align_to_current: bool,
) -> ImportBatch:
    if batch.status == ImportStatus.committed:
        raise DomainError("conflict", "This batch has already been committed", field=None)

    prepared = _prepare_transactions_import(db, batch, provider)
    if prepared.unmatched:
        raise DomainError(
            "validation",
            "Some rows reference instruments that still need to be matched or created",
            field="instruments",
        )

    pre_positions = {p.instrument_id: (p.units, p.cost_basis_gbp) for p in db.scalars(
        select(Position).where(Position.account_id == batch.account_id)
    ).all()}

    deleted_stand_ins: list[dict] = []
    if replace_stand_ins:
        stand_ins = _stand_in_rows(
            db, batch.account_id, prepared.instrument_ids, prepared.needs_cash_stand_in
        )
        for row in stand_ins:
            deleted_stand_ins.append(_serialise_txn(row))
            db.delete(row)
        db.flush()

    for row in prepared.kept_rows:
        key = row.instrument_key()
        instrument_id = prepared.matched.get(key) if key is not None else None
        db.add(
            Transaction(
                account_id=batch.account_id,
                status=TxnStatus.confirmed,
                source=TxnSource.import_,
                import_batch_id=batch.id,
                **_row_to_txn_kwargs(row, instrument_id),
            )
        )
    db.flush()

    if align_to_current:
        confirmed = ledger_service.confirmed_txns(db, batch.account_id)
        state = ledger.replay([ledger_service.to_engine_txn(r) for r in confirmed], strict=False)
        on = today()
        for instrument_id, (units, cost) in pre_positions.items():
            avg_cost = cost / units if units > 1e-9 else 0.0
            du, dc = ledger.position_target_adjustment(state, instrument_id, units, avg_cost)
            if abs(du) > 1e-9 or abs(dc) > 0.005:
                db.add(
                    Transaction(
                        account_id=batch.account_id,
                        instrument_id=instrument_id,
                        date=on,
                        type=TxnType.ADJUSTMENT,
                        units=round(du, 8),
                        amount_gbp=0.0,
                        cost_basis_gbp=round(dc, 2),
                        status=TxnStatus.confirmed,
                        source=TxnSource.import_,
                        import_batch_id=batch.id,
                    )
                )
        db.flush()

    warnings = ledger_service.rebuild_positions(db, batch.account_id)

    batch.status = ImportStatus.committed
    batch.imported_at = now_utc_naive()
    batch.rows_imported = len(prepared.kept_rows)
    batch.rows_skipped = prepared.rows_total - len(prepared.kept_rows)
    batch.deleted_stand_ins_json = json.dumps(deleted_stand_ins)
    dates = [r.date for r in prepared.kept_rows]
    if dates:
        batch.earliest_date = min(dates) if batch.earliest_date is None else min(batch.earliest_date, min(dates))
    db.commit()
    db.refresh(batch)

    logger.info("Import batch %s committed with %d warnings", batch.id, len(warnings))
    return batch


def commit_balances(
    db: Session,
    batch: ImportBatch,
    anchor_balance_gbp: float | None,
    anchor_date: date | None,
) -> ImportBatch:
    if batch.status == ImportStatus.committed:
        raise DomainError("conflict", "This batch has already been committed", field=None)

    from app.models.balances import BalanceEntry

    rows, errors = _parse_bank(batch)
    balances = compute_daily_balances(rows, anchor_balance_gbp, anchor_date)
    if not balances:
        raise DomainError("validation", "No balances to import", field=None)

    # Snapshot whatever was there before, per date, so rollback can restore it exactly —
    # a date this import writes may have had a pre-existing manual/statement entry.
    previous: list[dict] = []
    for d, balance in balances.items():
        entry = db.scalars(
            select(BalanceEntry).where(BalanceEntry.account_id == batch.account_id, BalanceEntry.date == d)
        ).first()
        if entry is None:
            entry = BalanceEntry(account_id=batch.account_id, date=d)
            db.add(entry)
        else:
            previous.append(
                {
                    "date": d.isoformat(),
                    "balance_gbp": entry.balance_gbp,
                    "source": entry.source.value,
                    "notes": entry.notes,
                }
            )
        entry.balance_gbp = round(balance, 2)
        entry.source = BalanceSource.csv

    batch.status = ImportStatus.committed
    batch.imported_at = now_utc_naive()
    batch.rows_imported = len(balances)
    batch.rows_skipped = len(rows) + len(errors) - len(balances)
    batch.earliest_date = min(balances.keys())
    # Repurpose mapping_json (spent, post-commit, for a balances batch) to remember exactly
    # which dates this commit wrote, so rollback deletes only those and not neighbouring
    # manually-entered balances; deleted_stand_ins_json holds the previous values to restore.
    batch.mapping_json = json.dumps({"committed_dates": sorted(d.isoformat() for d in balances)})
    batch.deleted_stand_ins_json = json.dumps(previous)
    db.commit()
    db.refresh(batch)
    return batch


def commit(
    db: Session,
    batch: ImportBatch,
    provider: PriceProvider | None,
    replace_stand_ins: bool,
    align_to_current: bool,
    anchor_balance_gbp: float | None,
    anchor_date: date | None,
) -> ImportBatch:
    if batch.kind == ImportKind.transactions:
        batch = commit_transactions(db, batch, provider, replace_stand_ins, align_to_current)
    else:
        batch = commit_balances(db, batch, anchor_balance_gbp, anchor_date)

    job_id = start_rebuild_job(batch.account_id, batch.earliest_date or today(), provider)
    return batch, job_id


# ---------------------------------------------------------------------------
# Rebuild history (background job with progress) — docs/06-imports-future.md step 8
# ---------------------------------------------------------------------------


@dataclass
class JobStatus:
    status: str = "pending"  # pending | running | done | error
    progress: float = 0.0
    error: str | None = None


_jobs: dict[str, JobStatus] = {}
_jobs_lock = threading.Lock()


def _run_rebuild_job(job_id: str, account_id: int, from_date: date, provider: PriceProvider) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "running"
        _jobs[job_id].progress = 0.1
    try:
        with SessionLocal() as db:
            account = db.get(Account, account_id)
            if account is not None:
                instrument_ids = list(
                    db.scalars(
                        select(Transaction.instrument_id)
                        .where(Transaction.account_id == account_id, Transaction.instrument_id.isnot(None))
                        .distinct()
                    ).all()
                )
                if instrument_ids:
                    price_service.ensure_history(db, provider, instrument_ids, from_date, today())
                with _jobs_lock:
                    _jobs[job_id].progress = 0.5
                snapshot_service.rebuild(db, account_id, from_date)
        with _jobs_lock:
            _jobs[job_id].status = "done"
            _jobs[job_id].progress = 1.0
    except Exception as exc:  # noqa: BLE001
        logger.exception("Import rebuild job %s failed", job_id)
        with _jobs_lock:
            _jobs[job_id].status = "error"
            _jobs[job_id].error = str(exc)


def start_rebuild_job(account_id: int, from_date: date, provider: PriceProvider | None = None) -> str:
    from app.providers.yahoo import YahooProvider

    job_id = str(uuid.uuid4())
    provider = provider or YahooProvider()
    with _jobs_lock:
        _jobs[job_id] = JobStatus()
    threading.Thread(
        target=_run_rebuild_job, args=(job_id, account_id, from_date, provider), daemon=True
    ).start()
    return job_id


def get_job(job_id: str) -> JobStatus | None:
    with _jobs_lock:
        return _jobs.get(job_id)


# ---------------------------------------------------------------------------
# Rollback — docs/06-imports-future.md step 9
# ---------------------------------------------------------------------------


def rollback(db: Session, batch: ImportBatch) -> ImportBatch:
    if batch.status != ImportStatus.committed:
        raise DomainError("validation", "Only a committed batch can be rolled back", field=None)

    account_id = batch.account_id

    if batch.kind == ImportKind.transactions:
        db.query(Transaction).filter(Transaction.import_batch_id == batch.id).delete(synchronize_session=False)
        db.flush()

        deleted = json.loads(batch.deleted_stand_ins_json) if batch.deleted_stand_ins_json else []
        for item in deleted:
            db.add(
                Transaction(
                    account_id=item["account_id"],
                    instrument_id=item["instrument_id"],
                    date=date.fromisoformat(item["date"]),
                    type=TxnType(item["type"]),
                    units=item["units"],
                    price_native=item["price_native"],
                    currency=item["currency"],
                    fx_gbp_per_unit=item["fx_gbp_per_unit"],
                    amount_gbp=item["amount_gbp"],
                    fees_gbp=item["fees_gbp"],
                    cost_basis_gbp=item["cost_basis_gbp"],
                    split_ratio=item["split_ratio"],
                    contribution_source=ContributionSource(item["contribution_source"])
                    if item["contribution_source"]
                    else None,
                    status=TxnStatus(item["status"]),
                    source=TxnSource(item["source"]),
                    notes=item["notes"],
                )
            )
        db.flush()
        ledger_service.rebuild_positions(db, account_id)
    else:
        from app.models.balances import BalanceEntry

        committed_dates: list[date] = []
        if batch.mapping_json:
            committed_dates = [
                date.fromisoformat(d) for d in json.loads(batch.mapping_json).get("committed_dates", [])
            ]
        elif batch.earliest_date is not None:
            committed_dates = [batch.earliest_date]

        if committed_dates:
            db.query(BalanceEntry).filter(
                BalanceEntry.account_id == account_id, BalanceEntry.date.in_(committed_dates)
            ).delete(synchronize_session=False)
        db.flush()

        previous = json.loads(batch.deleted_stand_ins_json) if batch.deleted_stand_ins_json else []
        for item in previous:
            db.add(
                BalanceEntry(
                    account_id=account_id,
                    date=date.fromisoformat(item["date"]),
                    balance_gbp=item["balance_gbp"],
                    source=BalanceSource(item["source"]),
                    notes=item["notes"],
                )
            )
        db.flush()

    batch.status = ImportStatus.rolled_back
    db.commit()
    db.refresh(batch)

    snapshot_service.rebuild(db, account_id, batch.earliest_date or today())
    return batch
