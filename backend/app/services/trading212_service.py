"""Trading 212 API sync: pulls an account's orders, dividends and cash movements and feeds them
through the Phase 8 import pipeline (services/importers), so dedupe, instrument matching,
reconciliation, stand-in replacement and Undo all behave exactly like a CSV import.

- A sync that changes holdings (units) stops before writing: the batch is previewed and left
  pending, and the app pops up the changes wherever the user is (`pending_changes`), to accept
  (`accept`). The first sync always waits, as does anything with an unmatched instrument, a
  corporate action or new ledger warnings. Accepting replaces quick-entry stand-ins for the
  holdings involved: Trading 212's history is the real record.
- Syncs that only move cash (deposits, dividends, interest, fees) commit on their own.
- The API has no endpoint for scheduled deposits or AutoInvest, so Regular Payments keep driving
  projections. What changes is that a linked account never *records* them (`auto_record` is off
  and `record_due` skips it): the real transactions arrive through this sync instead.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import LONDON, UTC, now_utc_naive
from app.core.enums import (
    Category,
    ImportKind,
    ImportStatus,
    TxnSource,
    TxnStatus,
    TxnType,
    ValuationMethod,
    Wrapper,
)
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.db import SessionLocal
from app.models.accounts import Account
from app.models.broker_links import BrokerLink
from app.models.imports import ImportBatch
from app.models.instruments import Instrument
from app.models.recurring import RecurringPlan
from app.models.transactions import Transaction
from app.providers.base import PriceProvider
from app.providers.trading212 import Trading212Client, Trading212Error
from app.schemas.account import AccountCreate, OwnerShareIn
from app.schemas.instrument import InstrumentCreate
from app.services import account_service, broker_secrets, instrument_service
from app.services.broker_secrets import BrokerCredentials
from app.services.importers import matching
from app.services.importers import service as importer
from app.services.importers.canonical import CANONICAL_TXN_COLUMNS

logger = logging.getLogger("app.trading212")

PROVIDER = "trading212"
# Import profile name: scopes the ticker -> instrument aliases this sync saves.
PROFILE = "Trading 212 API"

ClientFactory = Callable[[BrokerCredentials, str], Trading212Client]


def _default_client(creds: BrokerCredentials, environment: str) -> Trading212Client:
    return Trading212Client(creds.api_key, creds.api_secret, environment)


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


def get_link(db: Session, account_id: int) -> BrokerLink | None:
    link = db.get(BrokerLink, account_id)
    if link is not None and link.pending_batch_id is not None:
        # The pending batch may have been accepted, or undone on the Import page since.
        batch = db.get(ImportBatch, link.pending_batch_id)
        if batch is None or batch.status in (ImportStatus.committed, ImportStatus.rolled_back):
            link.pending_batch_id = None
            if link.status == "needs_review":
                committed = batch is not None and batch.status == ImportStatus.committed
                link.status = "synced" if committed else "idle"
                link.status_message = None
            db.commit()
    return link


def is_linked(db: Session, account_id: int) -> bool:
    return db.get(BrokerLink, account_id) is not None


def list_links(db: Session) -> list[BrokerLink]:
    return list(db.scalars(select(BrokerLink)).all())


def check_key(
    api_key: str, api_secret: str, environment: str, client_factory: ClientFactory = _default_client
) -> BrokerCredentials:
    """Ask Trading 212 whether the key works, before anything is saved or created."""
    api_key, api_secret = api_key.strip(), api_secret.strip()
    if not api_key:
        raise DomainError("validation", "Paste the API key from the Trading 212 app", field="api_key")
    if environment not in ("live", "demo"):
        raise DomainError("validation", "Environment must be live or demo", field="environment")
    creds = BrokerCredentials(api_key=api_key, api_secret=api_secret)
    try:
        with client_factory(creds, environment) as client:
            summary = client.account_summary()
    except Trading212Error as exc:
        raise DomainError("validation", str(exc), field="api_key") from exc
    currency = str(summary.get("currency") or "GBP").upper()
    if currency != "GBP":
        raise DomainError(
            "validation", f"This Trading 212 account is in {currency}; only GBP accounts are supported", field="api_key"
        )
    return creds


def _require_holdings(account: Account) -> None:
    if account.valuation_method != ValuationMethod.holdings:
        raise DomainError(
            "validation", "Only holdings accounts (ISA/GIA with shares) can sync from Trading 212", field="account_id"
        )


def _attach(db: Session, account_id: int, creds: BrokerCredentials, environment: str) -> BrokerLink:
    broker_secrets.save(PROVIDER, account_id, creds)

    link = db.get(BrokerLink, account_id)
    if link is None:
        link = BrokerLink(account_id=account_id, provider=PROVIDER)
        db.add(link)
    link.environment = environment
    link.key_hint = creds.api_key[-4:]
    link.status = "idle"
    link.status_message = None

    # Real payments now arrive through the sync, so plans must stop recording their own copies
    # (they still drive projections). Pending, unconfirmed copies already written would double
    # count the moment the real ones land.
    for plan in db.scalars(select(RecurringPlan).where(RecurringPlan.account_id == account_id)).all():
        plan.auto_record = False
    db.query(Transaction).filter(
        Transaction.account_id == account_id,
        Transaction.source == TxnSource.recurring,
        Transaction.status == TxnStatus.pending,
    ).delete(synchronize_session=False)

    db.commit()
    db.refresh(link)
    return link


def connect(
    db: Session,
    account_id: int,
    api_key: str,
    api_secret: str,
    environment: str = "live",
    client_factory: ClientFactory = _default_client,
) -> BrokerLink:
    """Link an existing holdings account."""
    _require_holdings(account_service.get_account(db, account_id))
    creds = check_key(api_key, api_secret, environment, client_factory)
    return _attach(db, account_id, creds, environment)


ACCOUNT_TYPES = {"isa": (Wrapper.isa, "Trading 212 Stocks ISA"), "invest": (Wrapper.gia, "Trading 212 Invest")}


def connect_new_account(
    db: Session,
    account_type: str,
    owner_person_id: int,
    api_key: str,
    api_secret: str,
    environment: str = "live",
    name: str | None = None,
    client_factory: ClientFactory = _default_client,
) -> BrokerLink:
    """Settings → Connect Trading 212: the API can't say whether a key belongs to a Stocks ISA or
    an Invest account, so the user picks, and the holdings account is created to match. The key
    is checked first, so a bad key never leaves an empty account behind."""
    if account_type not in ACCOUNT_TYPES:
        raise DomainError("validation", "Choose Stocks ISA or Invest", field="account_type")
    creds = check_key(api_key, api_secret, environment, client_factory)
    wrapper, default_name = ACCOUNT_TYPES[account_type]
    account = account_service.create_account(
        db,
        AccountCreate(
            name=(name or "").strip() or default_name,
            category=Category.investment,
            wrapper=wrapper,
            valuation_method=ValuationMethod.holdings,
            provider="Trading 212",
            owners=[OwnerShareIn(person_id=owner_person_id, share=1.0)],
        ),
    )
    return _attach(db, account.id, creds, environment)


def set_auto_sync(db: Session, account_id: int, auto_sync: bool) -> BrokerLink:
    link = _require_link(db, account_id)
    link.auto_sync = auto_sync
    db.commit()
    db.refresh(link)
    return link


def disconnect(db: Session, account_id: int) -> None:
    """Forget the key and the link. Transactions already synced stay: they're real history."""
    link = db.get(BrokerLink, account_id)
    broker_secrets.delete(PROVIDER, account_id)
    if link is not None:
        _discard_pending_batch(db, link)
        db.delete(link)
        db.commit()


def _require_link(db: Session, account_id: int) -> BrokerLink:
    link = get_link(db, account_id)
    if link is None:
        raise NotFoundError(f"Account {account_id} isn't linked to Trading 212")
    return link


# ---------------------------------------------------------------------------
# Trading 212 JSON -> canonical CSV rows
# ---------------------------------------------------------------------------


def _money(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _london_date(stamp: str | None) -> date:
    if not stamp:
        raise ValueError("missing date")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(LONDON).date()


def _currency(code: str | None) -> str:
    code = (code or "GBP").strip()
    # Trading 212 says GBX for pence; the app's convention (engine/prices.py) is GBp.
    return "GBp" if code.upper() == "GBX" else code.upper()


def _fallback_id(prefix: str, *parts: object) -> str:
    return f"t212:{prefix}:" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


@dataclass
class ConvertedHistory:
    rows: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    corporate_actions: int = 0


def _row(**values: object) -> dict:
    row = {col: "" for col in CANONICAL_TXN_COLUMNS}
    row.update({k: ("" if v is None else v) for k, v in values.items()})
    return row


def order_external_id(item: dict) -> str | None:
    fill = item.get("fill")
    if not fill:
        return None
    if fill.get("id") is not None:
        return f"t212:fill:{fill['id']}"
    order = item.get("order") or {}
    return f"t212:order:{order.get('id')}"


def convert_order(item: dict, out: ConvertedHistory) -> None:
    order = item.get("order") or {}
    fill = item.get("fill")
    if not fill:
        return  # cancelled / rejected / still pending: no shares moved
    quantity = _money(fill.get("quantity"))
    if abs(quantity) < 1e-12:
        return

    wallet = fill.get("walletImpact") or {}
    wallet_ccy = (wallet.get("currency") or "GBP").upper()
    instrument = order.get("instrument") or {}
    ticker = instrument.get("ticker") or order.get("ticker")
    try:
        when = _london_date(fill.get("filledAt") or order.get("createdAt"))
    except ValueError:
        out.problems.append(f"Order {order.get('id')} has no fill date; skipped")
        return
    if wallet_ccy != "GBP":
        out.problems.append(f"Order {order.get('id')} ({ticker}) settled in {wallet_ccy}; skipped")
        return

    side = str(order.get("side") or ("SELL" if quantity < 0 else "BUY")).upper()
    units = abs(quantity)
    net = abs(_money(wallet.get("netValue")))
    price = fill.get("price")
    currency = _currency(instrument.get("currency") or order.get("currency"))
    fees = sum(
        abs(_money(t.get("quantity")))
        for t in wallet.get("taxes") or []
        if (t.get("currency") or "GBP").upper() == "GBP"
    )
    if currency == "GBP":
        fx = 1.0
    elif currency == "GBp":
        fx = 0.01
    elif price and units:
        fx = net / (units * float(price))
    else:
        fx = 1.0

    common = {
        "date": when.isoformat(),
        "symbol": ticker,
        "isin": instrument.get("isin"),
        "name": instrument.get("name"),
        "currency": currency,
        "fx_gbp_per_unit": round(fx, 8),
        "fees_gbp": round(fees, 2),
        "external_id": order_external_id(item),
    }

    fill_type = str(fill.get("type") or "TRADE").upper()
    if fill_type == "TRADE":
        out.rows.append(
            _row(
                **common,
                type="SELL" if side == "SELL" else "BUY",
                units=round(units, 8),
                price=price,
                amount_gbp=round(net if side == "SELL" else -net, 2),
                notes="Trading 212 AutoInvest" if order.get("initiatedFrom") == "AUTOINVEST" else None,
            )
        )
        return

    # Share transfers and corporate actions arrive as fills too. None of them moves cash: the
    # `netValue` Trading 212 reports is the value of the shares, not money paid. Always stop for
    # the user to check them.
    out.corporate_actions += 1
    outgoing = side == "SELL" or quantity < 0
    if fill_type in ("FOP", "FOP_CORRECTION"):
        # "Free of payment": shares moved in or out, e.g. an ISA transfer from another provider.
        # The value becomes the transferred-in cost basis (price x units x fx in the importer).
        out.rows.append(
            _row(
                **{**common, "currency": "GBP", "fx_gbp_per_unit": 1},
                type="TRANSFER_OUT" if outgoing else "TRANSFER_IN",
                units=round(units, 8),
                price=round(net / units, 8) if net and not outgoing else None,
                amount_gbp=0,
                notes="Trading 212 share transfer",
            )
        )
        return
    # Splits, stock dividends, mergers: units change, cost basis and cash don't.
    out.rows.append(
        _row(
            **common,
            type="ADJUSTMENT",
            units=round(-units if outgoing else units, 8),
            amount_gbp=0,
            notes=f"Trading 212 {fill_type.replace('_', ' ').lower()}",
        )
    )


def dividend_external_id(item: dict) -> str:
    if item.get("reference"):
        return f"t212:div:{item['reference']}"
    return _fallback_id("div", item.get("ticker"), item.get("paidOn"), item.get("amount"))


def convert_dividend(item: dict, out: ConvertedHistory) -> None:
    amount = _money(item.get("amount"))
    if abs(amount) < 0.005:
        return
    currency = (item.get("currency") or "GBP").upper()
    if currency != "GBP":
        out.problems.append(f"Dividend {item.get('reference')} paid in {currency}; skipped")
        return
    try:
        when = _london_date(item.get("paidOn"))
    except ValueError:
        out.problems.append(f"Dividend {item.get('reference')} has no date; skipped")
        return
    instrument = item.get("instrument") or {}
    base = {"date": when.isoformat(), "currency": "GBP", "fx_gbp_per_unit": 1, "external_id": dividend_external_id(item)}
    if amount > 0:
        out.rows.append(
            _row(
                **base,
                type="DIVIDEND",
                symbol=instrument.get("ticker") or item.get("ticker"),
                isin=instrument.get("isin"),
                name=instrument.get("name"),
                amount_gbp=round(amount, 2),
            )
        )
    else:  # a reversed or corrected dividend
        out.rows.append(
            _row(**base, type="TAX", amount_gbp=round(amount, 2), notes=f"Dividend correction {item.get('ticker') or ''}".strip())
        )


def transaction_external_id(item: dict) -> str:
    if item.get("reference"):
        return f"t212:txn:{item['reference']}"
    return _fallback_id("txn", item.get("type"), item.get("dateTime"), item.get("amount"))


def convert_transaction(item: dict, out: ConvertedHistory) -> None:
    amount = _money(item.get("amount"))
    if abs(amount) < 0.005:
        return
    currency = (item.get("currency") or "GBP").upper()
    kind = str(item.get("type") or "").upper()
    if currency != "GBP":
        out.problems.append(f"{kind or 'Transaction'} {item.get('reference')} in {currency}; skipped")
        return
    try:
        when = _london_date(item.get("dateTime"))
    except ValueError:
        out.problems.append(f"{kind or 'Transaction'} {item.get('reference')} has no date; skipped")
        return

    base = {"date": when.isoformat(), "currency": "GBP", "fx_gbp_per_unit": 1, "external_id": transaction_external_id(item)}
    if kind == "DEPOSIT":
        out.rows.append(_row(**base, type="DEPOSIT", amount_gbp=round(abs(amount), 2), contribution_source="personal"))
    elif kind == "WITHDRAW":
        out.rows.append(_row(**base, type="WITHDRAWAL", amount_gbp=round(-abs(amount), 2)))
    elif kind == "FEE":
        out.rows.append(_row(**base, type="FEE", amount_gbp=round(-abs(amount), 2)))
    elif kind == "TRANSFER":
        # Cash moved between the user's own Trading 212 accounts (e.g. Invest -> ISA).
        if amount > 0:
            out.rows.append(
                _row(**base, type="TRANSFER_IN", amount_gbp=round(amount, 2), contribution_source="transfer",
                     notes="Trading 212 transfer in")
            )
        else:
            out.rows.append(_row(**base, type="TRANSFER_OUT", amount_gbp=round(amount, 2), notes="Trading 212 transfer out"))
    elif kind in ("INTEREST_ON_FREE_CASH", "LENDING_INTEREST"):
        if amount > 0:
            out.rows.append(_row(**base, type="INTEREST", amount_gbp=round(amount, 2)))
        else:
            out.rows.append(_row(**base, type="FEE", amount_gbp=round(amount, 2), notes="Interest correction"))
    else:
        out.problems.append(f"Unrecognised Trading 212 transaction type {kind!r}; skipped")


# ---------------------------------------------------------------------------
# Instrument resolution
# ---------------------------------------------------------------------------

_T212_EXCHANGE_SUFFIX = {"l": ".L", "d": ".DE", "p": ".PA", "a": ".AS"}


def yahoo_symbol_guess(ticker: str | None) -> str | None:
    """Best guess at the Yahoo symbol for a Trading 212 ticker: `VUSAl_EQ` -> `VUSA.L`,
    `AAPL_US_EQ` -> `AAPL`. None when the format isn't one we know."""
    if not ticker:
        return None
    us = re.fullmatch(r"([A-Z0-9.]+)_US_EQ", ticker)
    if us:
        return us.group(1).replace(".", "-")
    other = re.fullmatch(r"([A-Z0-9.]+)([a-z])_EQ", ticker)
    if other and other.group(2) in _T212_EXCHANGE_SUFFIX:
        return other.group(1).rstrip(".") + _T212_EXCHANGE_SUFFIX[other.group(2)]
    return None


def _create_from_isin_search(
    db: Session, provider: PriceProvider, isin: str, name: str | None
) -> Instrument | None:
    try:
        hits = provider.search(isin)
    except Exception:  # noqa: BLE001 — no search result just leaves it for the user to match
        return None
    for hit in hits[:3]:
        existing = instrument_service.get_by_symbol(db, hit.symbol)
        if existing is not None:
            return existing
        try:
            return instrument_service.create_instrument(db, provider, InstrumentCreate(symbol=hit.symbol, name=name or None))
        except DomainError:
            continue
    return None


def resolve_instruments(db: Session, rows: list[dict], provider: PriceProvider | None) -> list[str]:
    """Pin every Trading 212 ticker in `rows` to an instrument, saving the choice as an alias for
    the import matcher. Order: saved alias -> ISIN -> guessed Yahoo symbol -> create it from Yahoo
    -> the first Yahoo search hit for the ISIN (e.g. Lennar bought on gettex, `LNNd_EQ`, has no
    `LNN.DE` on Yahoo but its ISIN finds `LEN`). Returns the tickers still unmatched."""
    seen: dict[str, dict] = {}
    for row in rows:
        if row.get("symbol") and row["type"] in ("BUY", "SELL", "DIVIDEND", "ADJUSTMENT", "TRANSFER_IN", "TRANSFER_OUT"):
            seen.setdefault(row["symbol"], row)

    unmatched: list[str] = []
    for ticker, row in seen.items():
        instrument_id = matching._alias_lookup(db, PROFILE, ticker)
        if instrument_id is not None:
            continue
        instrument: Instrument | None = None
        isin = row.get("isin") or None
        if isin:
            instrument = db.scalars(select(Instrument).where(Instrument.isin == isin)).first()
        guess = yahoo_symbol_guess(ticker)
        if instrument is None and guess:
            instrument = instrument_service.get_by_symbol(db, guess)
        if instrument is None and guess and provider is not None:
            try:
                instrument = instrument_service.create_instrument(
                    db, provider, InstrumentCreate(symbol=guess, name=row.get("name") or None)
                )
            except DomainError:
                instrument = None
        if instrument is None and isin and provider is not None:
            instrument = _create_from_isin_search(db, provider, isin, row.get("name"))
        if instrument is None:
            unmatched.append(ticker)
            continue
        if isin and not instrument.isin:
            instrument.isin = isin
        matching.save_alias(db, PROFILE, ticker, instrument.id)
        db.commit()
    return unmatched


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


_LEGACY_FILL_ID = re.compile(r"(?:T212-)?EOF(\d+)", re.IGNORECASE)


def _known_external_ids(db: Session, account_id: int) -> set[str]:
    """The account's external ids in the sync's `t212:` form. Rows from an earlier Trading 212
    CSV import count too: their `T212-EOF<fill id>` / `T212-<reference>` ids name the same fills
    and cash movements the API returns."""
    known: set[str] = set()
    for eid in db.scalars(
        select(Transaction.external_id).where(
            Transaction.account_id == account_id, Transaction.external_id.isnot(None)
        )
    ).all():
        if eid.startswith("t212:"):
            known.add(eid)
            continue
        fill = _LEGACY_FILL_ID.fullmatch(eid)
        if fill:
            known.add(f"t212:fill:{fill.group(1)}")
            continue
        ref = eid[5:] if eid.upper().startswith("T212-") else eid
        known.update({f"t212:txn:{ref}", f"t212:div:{ref}"})
    return known


def _fingerprint(on: str, units: object, amount: object) -> tuple[str, float, float]:
    return (on, round(abs(_money(units)), 6), round(_money(amount), 2))


def _drop_already_recorded(db: Session, account_id: int, rows: list[dict]) -> list[dict]:
    """Rows the account already has under a different id (e.g. a CSV-imported dividend whose
    reference differs from the API's) are the same event when date, units and cash match.
    Quick-entry stand-ins are left out: the import replaces those rather than matching them."""
    from collections import Counter

    existing = Counter(
        _fingerprint(t.date.isoformat(), t.units, t.amount_gbp)
        for t in db.scalars(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.status == TxnStatus.confirmed,
                Transaction.type.notin_([TxnType.OPENING_BALANCE, TxnType.ADJUSTMENT]),
                or_(Transaction.external_id.is_(None), Transaction.external_id.notlike("t212:%")),
            )
        ).all()
    )
    kept = []
    for row in rows:
        key = _fingerprint(row["date"], row.get("units"), row.get("amount_gbp"))
        if existing[key] > 0:
            existing[key] -= 1
            continue
        kept.append(row)
    return kept


def _stop_when_known(known: set[str], id_of: Callable[[dict], str | None], date_of: Callable[[dict], str | None]):
    """Stop paging once a whole page is already in the ledger, but only while the API is
    returning newest-first; if it ever pages oldest-first, read everything rather than risk
    stopping before the new items."""

    def stop(items: list[dict]) -> bool:
        if not items or not known:
            return False
        stamps = [s for s in (date_of(i) for i in items) if s]
        if stamps != sorted(stamps, reverse=True):
            return False
        return all((eid is None) or (eid in known) for eid in (id_of(i) for i in items))

    return stop


def fetch_history(client: Trading212Client, known: set[str]) -> ConvertedHistory:
    out = ConvertedHistory()
    for item in client.orders(
        _stop_when_known(known, order_external_id, lambda i: (i.get("fill") or {}).get("filledAt") or (i.get("order") or {}).get("createdAt"))
    ):
        convert_order(item, out)
    for item in client.dividends(_stop_when_known(known, dividend_external_id, lambda i: i.get("paidOn"))):
        convert_dividend(item, out)
    for item in client.transactions(_stop_when_known(known, transaction_external_id, lambda i: i.get("dateTime"))):
        convert_transaction(item, out)
    return out


def _is_corporate_action(row: dict) -> bool:
    """A share transfer or unit adjustment (see convert_order); cash transfers carry no symbol."""
    return row["type"] == "ADJUSTMENT" or (row["type"] in ("TRANSFER_IN", "TRANSFER_OUT") and bool(row.get("symbol")))


def _to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CANONICAL_TXN_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows, key=lambda r: (r["date"], r["external_id"])):
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _discard_pending_batch(db: Session, link: BrokerLink) -> None:
    if link.pending_batch_id is None:
        return
    batch = db.get(ImportBatch, link.pending_batch_id)
    link.pending_batch_id = None
    if batch is not None and batch.status in (ImportStatus.pending, ImportStatus.previewed):
        db.delete(batch)
    db.flush()


def _has_committed_sync(db: Session, account_id: int) -> bool:
    return (
        db.scalars(
            select(ImportBatch.id).where(
                ImportBatch.account_id == account_id,
                ImportBatch.profile_name == PROFILE,
                ImportBatch.status == ImportStatus.committed,
            )
        ).first()
        is not None
    )


def sync_account(
    db: Session,
    account_id: int,
    provider: PriceProvider | None,
    client_factory: ClientFactory = _default_client,
) -> BrokerLink:
    link = _require_link(db, account_id)
    creds = broker_secrets.load(PROVIDER, account_id)
    if creds is None:
        link.status, link.status_message = "error", "The saved API key is missing. Connect the account again."
        db.commit()
        return link

    link.status, link.status_message = "running", None
    db.commit()

    try:
        known = _known_external_ids(db, account_id)
        with client_factory(creds, link.environment) as client:
            history = fetch_history(client, known)

        new_rows = _drop_already_recorded(
            db, account_id, [r for r in history.rows if r["external_id"] not in known]
        )
        _discard_pending_batch(db, link)
        link.last_synced_at = now_utc_naive()
        link.last_new_rows = len(new_rows)

        if not new_rows:
            link.status = "up_to_date"
            link.status_message = "; ".join(history.problems) or None
            db.commit()
            return link

        unmatched = resolve_instruments(db, new_rows, provider)

        filename = f"trading212-{now_utc_naive():%Y%m%d-%H%M%S}.csv"
        batch, _headers, _sample, _profile = importer.upload(db, ImportKind.transactions, account_id, filename, _to_csv(new_rows))
        batch.profile_name = PROFILE
        db.commit()

        reasons: list[str] = []
        if not _has_committed_sync(db, account_id):
            reasons.append("First sync: your Trading 212 history is ready to add")
        if unmatched:
            reasons.append(f"{len(unmatched)} instrument(s) need matching: {', '.join(unmatched[:5])}")
        # Only new ones: the history read always overlaps what's already recorded.
        corporate_actions = sum(1 for r in new_rows if _is_corporate_action(r))
        if corporate_actions:
            reasons.append(f"{corporate_actions} share transfer(s) or corporate action(s) to check")
        if history.problems:
            reasons.extend(history.problems[:3])
        trades = sum(1 for r in new_rows if r["type"] in ("BUY", "SELL"))
        if trades and not reasons:
            reasons.append("1 new trade" if trades == 1 else f"{trades} new trades")
        if not reasons:
            new_warnings = importer.new_ledger_warnings(db, batch, provider)
            if new_warnings:
                reasons.append(new_warnings[0])

        if reasons:
            importer.preview(db, batch, provider)
            link.status = "needs_review"
            link.pending_batch_id = batch.id
            link.status_message = "; ".join(reasons)
            db.commit()
            return link

        importer.commit(db, batch, provider, replace_stand_ins=False, align_to_current=False,
                        anchor_balance_gbp=None, anchor_date=None)
        link.status = "synced"
        link.status_message = None
        db.commit()
        return link
    except Trading212Error as exc:
        db.rollback()
        link = _require_link(db, account_id)
        link.status, link.status_message = "error", str(exc)
        link.last_synced_at = now_utc_naive()  # "last checked" covers failed attempts too
        db.commit()
        return link
    except Exception as exc:
        logger.exception("Trading 212 sync failed for account %s", account_id)
        db.rollback()
        link = _require_link(db, account_id)
        link.status, link.status_message = "error", f"Sync failed: {exc}"
        link.last_synced_at = now_utc_naive()
        db.commit()
        return link


# ---------------------------------------------------------------------------
# Pending changes: shown in a popup, accepted in one click
# ---------------------------------------------------------------------------


@dataclass
class PendingChanges:
    link: BrokerLink
    account_name: str
    batch_id: int
    first_sync: bool
    rows: list[importer.CanonicalRow]
    preview: importer.PreviewResult
    cash_before_gbp: float
    cash_after_gbp: float


def pending_changes(db: Session, account_id: int) -> PendingChanges | None:
    """What accepting the account's waiting sync would do. No network: instruments were already
    resolved during the sync, and anything left over is matched in the popup."""
    link = get_link(db, account_id)
    if link is None or link.pending_batch_id is None:
        return None
    batch = importer.get_batch(db, link.pending_batch_id)
    account = account_service.get_account(db, account_id)
    preview = importer.preview(db, batch, None)
    cash_before = round(account.cash_balance_gbp, 2)
    return PendingChanges(
        link=link,
        account_name=account.name,
        batch_id=batch.id,
        first_sync=not _has_committed_sync(db, account_id),
        rows=importer.pending_rows(db, batch),
        preview=preview,
        cash_before_gbp=cash_before,
        cash_after_gbp=round(cash_before + (preview.cash_diff_gbp or 0.0), 2),
    )


def list_pending_changes(db: Session) -> list[PendingChanges]:
    return [c for c in (pending_changes(db, link.account_id) for link in list_links(db)) if c is not None]


def accept(db: Session, account_id: int, provider: PriceProvider | None) -> BrokerLink:
    """Commit the waiting sync. Quick-entry stand-ins for the holdings in it are replaced, which
    is what the popup's before/after figures show."""
    link = _require_link(db, account_id)
    if link.pending_batch_id is None:
        raise ConflictError("There are no Trading 212 changes waiting for this account")
    batch = importer.get_batch(db, link.pending_batch_id)
    importer.commit(db, batch, provider, replace_stand_ins=True, align_to_current=False,
                    anchor_balance_gbp=None, anchor_date=None)
    return _require_link(db, account_id)


# ---------------------------------------------------------------------------
# Background running
# ---------------------------------------------------------------------------

_running: set[int] = set()
_running_lock = threading.Lock()


def _run_in_thread(account_id: int, provider: PriceProvider | None, client_factory: ClientFactory) -> None:
    try:
        with SessionLocal() as db:
            sync_account(db, account_id, provider, client_factory)
    except Exception:
        logger.exception("Trading 212 background sync failed for account %s", account_id)
    finally:
        with _running_lock:
            _running.discard(account_id)


def start_sync(
    db: Session,
    account_id: int,
    provider: PriceProvider | None,
    client_factory: ClientFactory = _default_client,
) -> BrokerLink:
    """Run a sync in the background (the history endpoints allow 6 requests a minute, so a
    first sync with a long history can take a few minutes). The link's status tracks it."""
    link = _require_link(db, account_id)
    with _running_lock:
        if account_id in _running:
            return link
        _running.add(account_id)
    link.status, link.status_message = "running", None
    db.commit()
    db.refresh(link)
    threading.Thread(target=_run_in_thread, args=(account_id, provider, client_factory), daemon=True).start()
    return link


def _run_all_in_thread(account_ids: list[int], provider: PriceProvider | None, client_factory: ClientFactory) -> None:
    for account_id in account_ids:
        _run_in_thread(account_id, provider, client_factory)


def start_sync_all(
    db: Session,
    provider: PriceProvider | None,
    client_factory: ClientFactory = _default_client,
) -> list[BrokerLink]:
    """Update prices: sync every linked account in the background, one after another (they share
    the SQLite database). Accounts already syncing are left to finish."""
    links = list_links(db)
    started: list[int] = []
    for link in links:
        with _running_lock:
            if link.account_id in _running:
                continue
            _running.add(link.account_id)
        link.status, link.status_message = "running", None
        started.append(link.account_id)
    db.commit()
    if started:
        threading.Thread(target=_run_all_in_thread, args=(started, provider, client_factory), daemon=True).start()
    return links


def is_running(account_id: int) -> bool:
    with _running_lock:
        return account_id in _running


def sync_all(db: Session, provider: PriceProvider | None) -> int:
    """Scheduled job: sync every account with auto-sync on, one after another."""
    count = 0
    for link in list_links(db):
        if not link.auto_sync:
            continue
        with _running_lock:
            if link.account_id in _running:
                continue
            _running.add(link.account_id)
        try:
            sync_account(db, link.account_id, provider)
            count += 1
        finally:
            with _running_lock:
                _running.discard(link.account_id)
    return count


def reset_interrupted(db: Session) -> None:
    """A sync that was running when the app closed never finished; don't show it as running."""
    for link in list_links(db):
        if link.status == "running" and not is_running(link.account_id):
            link.status, link.status_message = "error", "The last sync was interrupted. Sync again."
    db.commit()
