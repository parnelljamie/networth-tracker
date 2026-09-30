"""Trading 212 API sync: JSON -> canonical rows, link/unlink, first sync stops for review, later
syncs commit on their own, reruns dedupe, and linked accounts never record Regular Payments."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.enums import (
    Category,
    Frequency,
    ImportStatus,
    PlanKind,
    PriceSource,
    TxnSource,
    TxnStatus,
    TxnType,
    ValuationMethod,
    Wrapper,
)
from app.core.errors import ConflictError, DomainError
from app.models.accounts import Account
from app.models.instruments import Instrument
from app.models.people import Person
from app.models.positions import Position
from app.models.recurring import RecurringPlan
from app.models.transactions import Transaction
from app.providers.trading212 import Trading212AuthError, Trading212Client
from app.schemas.account import AccountCreate, OwnerShareIn
from app.schemas.recurring import PlanAllocationIn, RecurringPlanCreate, RecurringPlanUpdate
from app.services import broker_secrets, recurring_service, trading212_service
from app.services.importers import service as importer
from app.services.trading212_service import ConvertedHistory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keys and import files are written under settings.data_dir."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def _order(fill_id: int, ticker: str, side: str, qty: float, price: float, net: float, filled_at: str,
           *, fill_type: str = "TRADE", initiated: str = "WEB", isin: str = "IE00B3XXRP09",
           name: str = "Vanguard S&P 500 UCITS ETF", currency: str = "GBX") -> dict:
    return {
        "order": {
            "id": fill_id * 10,
            "side": side,
            "status": "FILLED",
            "initiatedFrom": initiated,
            "ticker": ticker,
            "instrument": {"ticker": ticker, "isin": isin, "name": name, "currency": currency},
        },
        "fill": {
            "id": fill_id,
            "filledAt": filled_at,
            "price": price,
            "quantity": qty,
            "type": fill_type,
            "walletImpact": {"currency": "GBP", "netValue": net, "taxes": []},
        },
    }


def _deposit(ref: str, amount: float, when: str) -> dict:
    return {"type": "DEPOSIT", "amount": amount, "currency": "GBP", "dateTime": when, "reference": ref}


def _dividend(ref: str, amount: float, when: str, ticker: str = "VUSAl_EQ") -> dict:
    return {
        "reference": ref, "amount": amount, "currency": "GBP", "paidOn": when, "ticker": ticker,
        "quantity": 10, "instrument": {"ticker": ticker, "isin": "IE00B3XXRP09", "name": "Vanguard S&P 500"},
    }


class FakeClient:
    """Serves pages newest-first, like the real API, honouring the caller's early stop."""

    page_size = 2

    def __init__(self, orders=(), dividends=(), transactions=(), currency="GBP") -> None:
        self._data = {"orders": list(orders), "dividends": list(dividends), "transactions": list(transactions)}
        self.currency = currency
        self.pages_served = 0

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def account_summary(self) -> dict:
        return {"currency": self.currency, "id": 1, "totalValue": 0}

    def _paged(self, name: str, stop):
        items = self._data[name]
        for start in range(0, len(items), self.page_size):
            page = items[start:start + self.page_size]
            self.pages_served += 1
            yield from page
            if stop is not None and stop(page):
                return

    def orders(self, stop=None):
        return self._paged("orders", stop)

    def dividends(self, stop=None):
        return self._paged("dividends", stop)

    def transactions(self, stop=None):
        return self._paged("transactions", stop)


def _factory(client: FakeClient):
    return lambda creds, env: client


def _person(db: Session) -> Person:
    person = Person(name="James")
    db.add(person)
    db.commit()
    return person


def _isa(db: Session) -> Account:
    from app.services import account_service

    return account_service.create_account(
        db,
        AccountCreate(
            name="Trading 212 ISA", category=Category.investment, wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings, owners=[OwnerShareIn(person_id=_person(db).id, share=1.0)],
        ),
    )


def _instrument(db: Session, symbol: str = "VUSA.L") -> Instrument:
    instrument = Instrument(
        symbol=symbol, name="Vanguard S&P 500", quote_currency="GBP", price_source=PriceSource.manual,
        manual_price_gbp=80.0,
    )
    db.add(instrument)
    db.commit()
    return instrument


def _connect(db: Session, account: Account, client: FakeClient) -> None:
    trading212_service.connect(db, account.id, "key-abcd1234", "secret", client_factory=_factory(client))


def _positions(db: Session, account_id: int) -> dict[int, Position]:
    return {p.instrument_id: p for p in db.scalars(select(Position).where(Position.account_id == account_id))}


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def test_buy_and_sell_orders_become_signed_trades():
    out = ConvertedHistory()
    trading212_service.convert_order(
        _order(1, "VUSAl_EQ", "BUY", 10, 7512.5, 751.25, "2026-03-02T09:30:00Z", initiated="AUTOINVEST"), out
    )
    trading212_service.convert_order(_order(2, "VUSAl_EQ", "SELL", -4, 8000, 320.0, "2026-06-01T23:30:00Z"), out)
    buy, sell = out.rows
    assert buy["type"] == "BUY" and buy["units"] == 10 and buy["amount_gbp"] == -751.25
    assert buy["currency"] == "GBp" and buy["fx_gbp_per_unit"] == 0.01
    assert buy["external_id"] == "t212:fill:1" and buy["notes"] == "Trading 212 AutoInvest"
    assert sell["type"] == "SELL" and sell["units"] == 4 and sell["amount_gbp"] == 320.0
    # 23:30 UTC on 1 June is 00:30 on 2 June in London (BST).
    assert sell["date"] == "2026-06-02"


def test_unfilled_orders_are_ignored_and_corporate_actions_flagged():
    out = ConvertedHistory()
    cancelled = _order(3, "VUSAl_EQ", "BUY", 1, 1, 1, "2026-01-01T10:00:00Z")
    cancelled["fill"] = None
    trading212_service.convert_order(cancelled, out)
    trading212_service.convert_order(
        _order(4, "VUSAl_EQ", "BUY", 5, 0, 0, "2026-01-05T10:00:00Z", fill_type="STOCK_SPLIT"), out
    )
    assert len(out.rows) == 1
    assert out.rows[0]["type"] == "ADJUSTMENT" and out.rows[0]["units"] == 5
    assert out.corporate_actions == 1


def test_cash_movements_and_dividends_map_to_ledger_types():
    out = ConvertedHistory()
    for item in [
        _deposit("d1", 500, "2026-04-06T08:00:00Z"),
        {"type": "WITHDRAW", "amount": -100, "currency": "GBP", "dateTime": "2026-04-07T08:00:00Z", "reference": "w1"},
        {"type": "INTEREST_ON_FREE_CASH", "amount": 1.23, "currency": "GBP", "dateTime": "2026-04-08T08:00:00Z", "reference": "i1"},
        {"type": "TRANSFER", "amount": 250, "currency": "GBP", "dateTime": "2026-04-09T08:00:00Z", "reference": "t1"},
        {"type": "FEE", "amount": 2, "currency": "GBP", "dateTime": "2026-04-10T08:00:00Z", "reference": "f1"},
    ]:
        trading212_service.convert_transaction(item, out)
    trading212_service.convert_dividend(_dividend("div1", 4.56, "2026-04-11"), out)
    got = [(r["type"], r["amount_gbp"]) for r in out.rows]
    assert got == [
        ("DEPOSIT", 500), ("WITHDRAWAL", -100), ("INTEREST", 1.23), ("TRANSFER_IN", 250), ("FEE", -2),
        ("DIVIDEND", 4.56),
    ]
    assert out.rows[-1]["symbol"] == "VUSAl_EQ"


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [("VUSAl_EQ", "VUSA.L"), ("AAPL_US_EQ", "AAPL"), ("BRK.B_US_EQ", "BRK-B"), ("SAPd_EQ", "SAP.DE"),
     ("WEIRD", None), (None, None)],
)
def test_yahoo_symbol_guess(ticker, expected):
    assert trading212_service.yahoo_symbol_guess(ticker) == expected


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------


def test_connect_stores_key_outside_db_and_turns_off_plan_recording(db: Session):
    account = _isa(db)
    instrument = _instrument(db)
    with freeze_time("2026-09-01"):
        plan = recurring_service.create_plan(
            db, account,
            RecurringPlanCreate(
                account_id=account.id, name="Monthly", kind=PlanKind.contribution, amount_gbp=500,
                frequency=Frequency.monthly, day_of_month=1, start_date=date(2026, 8, 1), auto_record=True,
                allocations=[PlanAllocationIn(instrument_id=instrument.id, weight=1.0)],
            ),
        )
        recurring_service.record_due(db, date(2026, 9, 1))
    pending = db.scalars(select(Transaction).where(Transaction.source == TxnSource.recurring)).all()
    assert pending and all(t.status == TxnStatus.pending for t in pending)

    _connect(db, account, FakeClient())

    link = trading212_service.get_link(db, account.id)
    assert link is not None and link.key_hint == "1234" and link.environment == "live"
    creds = broker_secrets.load("trading212", account.id)
    assert creds is not None and creds.api_key == "key-abcd1234" and creds.api_secret == "secret"
    db.refresh(plan)
    assert plan.auto_record is False and plan.is_active is True
    assert db.scalars(select(Transaction).where(Transaction.source == TxnSource.recurring)).all() == []


def test_connect_rejects_non_gbp_and_bad_keys(db: Session):
    account = _isa(db)
    with pytest.raises(DomainError, match="EUR"):
        _connect(db, account, FakeClient(currency="EUR"))

    class Rejecting(FakeClient):
        def account_summary(self) -> dict:
            raise Trading212AuthError("Trading 212 rejected the API key.")

    with pytest.raises(DomainError, match="rejected"):
        _connect(db, account, Rejecting())
    assert trading212_service.get_link(db, account.id) is None
    assert broker_secrets.load("trading212", account.id) is None


def test_linked_account_refuses_auto_add_and_record_due_skips_it(db: Session):
    account = _isa(db)
    _connect(db, account, FakeClient())
    with pytest.raises(DomainError, match="Trading 212"):
        recurring_service.create_plan(
            db, account,
            RecurringPlanCreate(
                account_id=account.id, name="Monthly", kind=PlanKind.contribution, amount_gbp=500,
                frequency=Frequency.monthly, day_of_month=1, start_date=date(2026, 8, 1), auto_record=True,
            ),
        )
    plan = recurring_service.create_plan(
        db, account,
        RecurringPlanCreate(
            account_id=account.id, name="Monthly", kind=PlanKind.contribution, amount_gbp=500,
            frequency=Frequency.monthly, day_of_month=1, start_date=date(2026, 8, 1),
        ),
    )
    with pytest.raises(DomainError):
        recurring_service.update_plan(db, plan, RecurringPlanUpdate(auto_record=True))
    # Even a plan flagged directly in the database is not recorded for a linked account.
    db.get(RecurringPlan, plan.id).auto_record = True
    db.commit()
    assert recurring_service.record_due(db, date(2026, 9, 1)) == []


def test_disconnect_forgets_key_but_keeps_history(db: Session, fake_provider):
    account = _isa(db)
    _instrument(db)
    client = FakeClient(orders=[_order(1, "VUSAl_EQ", "BUY", 10, 7500, 750, "2026-03-02T09:30:00Z")],
                        transactions=[_deposit("d1", 1000, "2026-03-01T08:00:00Z")])
    _connect(db, account, client)
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    importer.commit(db, importer.get_batch(db, link.pending_batch_id), fake_provider, True, False, None, None)

    trading212_service.disconnect(db, account.id)
    assert trading212_service.get_link(db, account.id) is None
    assert broker_secrets.load("trading212", account.id) is None
    assert len(db.scalars(select(Transaction).where(Transaction.account_id == account.id)).all()) == 2


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def test_first_sync_waits_to_be_accepted_then_trades_wait_and_cash_commits_itself(db: Session, fake_provider):
    account = _isa(db)
    instrument = _instrument(db)
    history = FakeClient(
        orders=[
            _order(2, "VUSAl_EQ", "BUY", 5, 8000, 400.0, "2026-04-02T09:30:00Z", initiated="AUTOINVEST"),
            _order(1, "VUSAl_EQ", "BUY", 10, 7500, 750.0, "2026-03-02T09:30:00Z"),
        ],
        dividends=[_dividend("div1", 3.21, "2026-03-20")],
        transactions=[_deposit("d2", 500, "2026-04-01T08:00:00Z"), _deposit("d1", 1000, "2026-03-01T08:00:00Z")],
    )
    _connect(db, account, history)

    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(history))
    assert link.status == "needs_review" and "First sync" in (link.status_message or "")
    assert link.last_new_rows == 5
    batch = importer.get_batch(db, link.pending_batch_id)
    assert batch.status == ImportStatus.previewed and batch.profile_name == trading212_service.PROFILE
    assert _positions(db, account.id) == {}  # nothing written until the user accepts
    db.refresh(instrument)
    assert instrument.isin == "IE00B3XXRP09"  # learnt from Trading 212

    # The popup's view: every row, the holding before and after, and the cash.
    changes = trading212_service.pending_changes(db, account.id)
    assert changes is not None and changes.first_sync and changes.preview.ready
    assert len(changes.rows) == 5
    [holding] = changes.preview.reconciliation
    assert holding.current_units == 0 and holding.imported_units == pytest.approx(15)
    assert changes.cash_before_gbp == 0 and changes.cash_after_gbp == pytest.approx(1500 - 1150 + 3.21)
    assert [c.link.account_id for c in trading212_service.list_pending_changes(db)] == [account.id]

    link = trading212_service.accept(db, account.id, fake_provider)
    assert link.status == "synced" and link.pending_batch_id is None
    assert trading212_service.list_pending_changes(db) == []
    pos = _positions(db, account.id)[instrument.id]
    assert pos.units == pytest.approx(15)
    assert pos.cost_basis_gbp == pytest.approx(1150.0)
    assert db.get(Account, account.id).cash_balance_gbp == pytest.approx(1500 - 1150 + 3.21)
    with pytest.raises(ConflictError):
        trading212_service.accept(db, account.id, fake_provider)

    # Nothing new: no batch, status up to date.
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(history))
    assert link.status == "up_to_date" and link.last_new_rows == 0

    # Only cash moved: committed without asking.
    history._data["transactions"].insert(0, _deposit("d3", 500, "2026-05-01T08:00:00Z"))
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(history))
    assert link.status == "synced" and link.last_new_rows == 1 and link.pending_batch_id is None
    assert db.get(Account, account.id).cash_balance_gbp == pytest.approx(2000 - 1150 + 3.21)

    # A trade changes the holdings: it waits to be accepted.
    history._data["orders"].insert(
        0, _order(3, "VUSAl_EQ", "BUY", 6, 8300, 498.0, "2026-05-02T09:30:00Z", initiated="AUTOINVEST")
    )
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(history))
    assert link.status == "needs_review" and link.status_message == "1 new trade"
    changes = trading212_service.pending_changes(db, account.id)
    assert not changes.first_sync
    [holding] = changes.preview.reconciliation
    assert (holding.current_units, holding.imported_units) == (pytest.approx(15), pytest.approx(21))
    assert _positions(db, account.id)[instrument.id].units == pytest.approx(15)

    trading212_service.accept(db, account.id, fake_provider)
    assert _positions(db, account.id)[instrument.id].units == pytest.approx(21)
    buys = db.scalars(select(Transaction).where(Transaction.type == TxnType.BUY)).all()
    assert len(buys) == 3 and all(t.status == TxnStatus.confirmed for t in buys)


def test_sync_all_starts_every_link_once(db: Session, monkeypatch: pytest.MonkeyPatch):
    first = _isa(db)
    _connect(db, first, FakeClient())
    trading212_service.connect_new_account(
        db, "invest", first.owners[0].person_id, "key-efgh5678", "", client_factory=_factory(FakeClient())
    )
    second = db.scalars(select(Account).where(Account.id != first.id)).one()
    ran: list[list[int]] = []
    monkeypatch.setattr(trading212_service, "_run_all_in_thread", lambda ids, *_: ran.append(ids))

    class NoThread:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(trading212_service.threading, "Thread", NoThread)
    with trading212_service._running_lock:
        trading212_service._running.add(second.id)  # already syncing: left alone
    try:
        links = trading212_service.start_sync_all(db, None)
    finally:
        with trading212_service._running_lock:
            trading212_service._running.difference_update({first.id, second.id})
    assert ran == [[first.id]]
    assert {link.account_id for link in links} == {first.id, second.id}
    assert trading212_service.get_link(db, first.id).status == "running"


def test_incremental_sync_stops_paging_once_it_reaches_known_items(db: Session, fake_provider):
    account = _isa(db)
    _instrument(db)
    orders = [
        _order(i, "VUSAl_EQ", "BUY", 1, 8000, 80.0, f"2026-01-{10 + i:02d}T09:30:00Z")
        for i in range(1, 9)
    ]
    orders.sort(key=lambda o: o["fill"]["filledAt"], reverse=True)
    client = FakeClient(orders=orders, transactions=[_deposit("d1", 5000, "2026-01-01T08:00:00Z")])
    _connect(db, account, client)
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    importer.commit(db, importer.get_batch(db, link.pending_batch_id), fake_provider, True, False, None, None)

    client.pages_served = 0
    trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    # One page each for orders and transactions (dividends are empty): no walk through history.
    assert client.pages_served == 2


def test_unmatched_instrument_holds_even_a_later_sync_for_review(db: Session, fake_provider):
    account = _isa(db)
    _instrument(db)
    client = FakeClient(orders=[_order(1, "VUSAl_EQ", "BUY", 10, 7500, 750, "2026-03-02T09:30:00Z")],
                        transactions=[_deposit("d1", 1000, "2026-03-01T08:00:00Z")])
    _connect(db, account, client)
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    importer.commit(db, importer.get_batch(db, link.pending_batch_id), fake_provider, True, False, None, None)

    client._data["orders"].insert(
        0, _order(2, "ZZZZ_XX_EQ", "BUY", 1, 10, 10, "2026-04-02T09:30:00Z", isin="XX0000000000", name="Mystery plc")
    )
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    assert link.status == "needs_review" and "ZZZZ_XX_EQ" in (link.status_message or "")

    # Re-syncing replaces the stale pending batch rather than piling them up.
    from app.models.imports import ImportBatch

    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    waiting = db.scalars(
        select(ImportBatch).where(ImportBatch.account_id == account.id, ImportBatch.status != ImportStatus.committed)
    ).all()
    assert [b.id for b in waiting] == [link.pending_batch_id]


def test_sync_errors_are_reported_on_the_link(db: Session, fake_provider):
    account = _isa(db)
    _connect(db, account, FakeClient())

    class Broken(FakeClient):
        def orders(self, stop=None):
            raise Trading212AuthError("The API key is missing a permission.")

    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(Broken()))
    assert link.status == "error" and "permission" in (link.status_message or "")
    assert link.last_synced_at is not None  # issue #37: a failed attempt still counts as checked


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


def test_client_uses_basic_auth_pages_and_waits_out_rate_limits():
    calls: list[httpx.Request] = []
    slept: list[float] = []
    state = {"first": True}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/orders") and "cursor" not in request.url.query.decode():
            if state["first"]:
                state["first"] = False
                return httpx.Response(429, headers={"x-ratelimit-reset": "1005"})
            return httpx.Response(
                200,
                headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1010"},
                json={"items": [{"n": 1}], "nextPagePath": "/api/v0/equity/history/orders?limit=50&cursor=abc"},
            )
        return httpx.Response(200, json={"items": [{"n": 2}], "nextPagePath": None})

    client = Trading212Client(
        "KEY", "SECRET", "live", http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=slept.append, clock=lambda: 1000.0,
    )
    items = list(client.orders())
    assert items == [{"n": 1}, {"n": 2}]
    assert calls[0].headers["Authorization"] == "Basic S0VZOlNFQ1JFVA=="
    assert str(calls[0].url).startswith("https://live.trading212.com/api/v0/equity/history/orders")
    assert "cursor=abc" in str(calls[-1].url)
    assert slept == [5.5, 10.5]


def test_client_legacy_key_and_auth_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "LEGACYKEY"
        return httpx.Response(401, json={})

    client = Trading212Client("LEGACYKEY", "", "demo", http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Trading212AuthError):
        client.account_summary()


def test_secret_file_round_trips(isolated_data_dir: Path):
    broker_secrets.save("trading212", 7, broker_secrets.BrokerCredentials("k", "s"))
    assert broker_secrets.load("trading212", 7) == broker_secrets.BrokerCredentials("k", "s")
    raw = (isolated_data_dir / "secrets" / "trading212-7.key").read_bytes()
    import sys

    if sys.platform == "win32":
        assert raw.startswith(b"DPAPI1:") and b'"k"' not in raw
    else:
        assert json.loads(raw) == {"api_key": "k", "api_secret": "s"}
    broker_secrets.delete("trading212", 7)
    assert broker_secrets.load("trading212", 7) is None


# ---------------------------------------------------------------------------
# Issue #33: first sync over an account that already had a Trading 212 CSV import
# ---------------------------------------------------------------------------


def test_share_transfer_is_non_cash_with_its_value_as_cost_basis():
    out = ConvertedHistory()
    trading212_service.convert_order(
        _order(9, "VUKGl_EQ", "BUY", 50, 0, 2500.0, "2026-02-02T09:00:00Z", fill_type="FOP"), out
    )
    (row,) = out.rows
    assert row["type"] == "TRANSFER_IN" and row["units"] == 50 and row["amount_gbp"] == 0
    assert row["price"] == 50.0 and row["currency"] == "GBP"  # 50 units x £50 = £2,500 cost basis
    assert out.corporate_actions == 1

    split = ConvertedHistory()
    trading212_service.convert_order(
        _order(10, "VUSAl_EQ", "BUY", 5, 0, 400.0, "2026-02-03T09:00:00Z", fill_type="STOCK_SPLIT"), split
    )
    assert split.rows[0]["type"] == "ADJUSTMENT" and split.rows[0]["amount_gbp"] == 0


def test_sync_skips_trades_already_imported_from_a_trading212_csv(db: Session, fake_provider):
    account = _isa(db)
    instrument = _instrument(db)
    # What an earlier CSV import left behind: T212-EOF<fill id> and T212-<reference> ids, and a
    # dividend whose CSV reference doesn't match the API's.
    for kwargs in [
        dict(date=date(2026, 3, 1), type=TxnType.DEPOSIT, amount_gbp=1000.0, external_id="T212-dep-ref-1"),
        dict(date=date(2026, 3, 2), type=TxnType.BUY, instrument_id=instrument.id, units=10, amount_gbp=-750.0,
             external_id="T212-EOF1"),
        dict(date=date(2026, 3, 20), type=TxnType.DIVIDEND, instrument_id=instrument.id, amount_gbp=3.21,
             external_id="T212-somehash"),
    ]:
        db.add(Transaction(account_id=account.id, source=TxnSource.import_, **kwargs))
    db.commit()
    from app.services import ledger_service

    ledger_service.rebuild_positions(db, account.id)
    db.commit()

    client = FakeClient(
        orders=[
            _order(2, "VUSAl_EQ", "BUY", 4, 8000, 320.0, "2026-04-02T09:30:00Z"),
            _order(1, "VUSAl_EQ", "BUY", 10, 7500, 750.0, "2026-03-02T09:30:00Z"),
        ],
        dividends=[_dividend("api-div-ref", 3.21, "2026-03-20")],
        transactions=[_deposit("ref-2", 320, "2026-04-01T08:00:00Z"), _deposit("dep-ref-1", 1000, "2026-03-01T08:00:00Z")],
    )
    _connect(db, account, client)
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))

    assert link.last_new_rows == 2  # only the April deposit and buy are new
    batch = importer.get_batch(db, link.pending_batch_id)
    importer.commit(db, batch, fake_provider, True, False, None, None)
    assert _positions(db, account.id)[instrument.id].units == pytest.approx(14)


def test_unknown_listing_is_matched_through_an_isin_search(db: Session, fake_provider):
    from app.providers.base import InstrumentMetadata, InstrumentSearchResult

    fake_provider.set_search_results([InstrumentSearchResult("LEN", "Lennar Corporation", "NYQ", "EQUITY")])
    fake_provider.set_metadata("LEN", InstrumentMetadata("Lennar Corporation", "USD", "NYQ", "EQUITY"))
    rows = [{"type": "BUY", "symbol": "LNNd_EQ", "isin": "US5260571048", "name": "Lennar (Class A)"}]

    assert trading212_service.resolve_instruments(db, rows, fake_provider) == []
    created = db.scalars(select(Instrument).where(Instrument.symbol == "LEN")).one()
    assert created.isin == "US5260571048"


# ---------------------------------------------------------------------------
# Settings: connect and create the account in one go
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("account_type", "wrapper", "name"), [
    ("isa", Wrapper.isa, "Trading 212 Stocks ISA"), ("invest", Wrapper.gia, "Trading 212 Invest"),
])
def test_connect_new_account_creates_a_matching_holdings_account(db: Session, account_type, wrapper, name):
    owner = _person(db)
    link = trading212_service.connect_new_account(
        db, account_type, owner.id, "key-9999", "s", client_factory=_factory(FakeClient())
    )
    account = db.get(Account, link.account_id)
    assert account.wrapper == wrapper and account.name == name
    assert account.valuation_method == ValuationMethod.holdings and account.provider == "Trading 212"
    assert [o.person_id for o in account.owners] == [owner.id]
    assert broker_secrets.load("trading212", account.id).api_key == "key-9999"


def test_connect_new_account_creates_nothing_when_the_key_is_rejected(db: Session):
    owner = _person(db)

    class Rejecting(FakeClient):
        def account_summary(self) -> dict:
            raise Trading212AuthError("Trading 212 rejected the API key.")

    with pytest.raises(DomainError, match="rejected"):
        trading212_service.connect_new_account(db, "isa", owner.id, "bad", "", client_factory=_factory(Rejecting()))
    assert db.scalars(select(Account)).all() == []


def test_changes_and_accept_endpoints(db: Session, client, fake_provider):
    account = _isa(db)
    _instrument(db)
    history = FakeClient(orders=[_order(1, "VUSAl_EQ", "BUY", 10, 7500, 750, "2026-03-02T09:30:00Z")],
                         transactions=[_deposit("d1", 1000, "2026-03-01T08:00:00Z")])
    _connect(db, account, history)
    trading212_service.sync_account(db, account.id, fake_provider, _factory(history))

    [changes] = client.get("/api/trading212/changes").json()
    assert changes["account_id"] == account.id and changes["first_sync"] and changes["ready"]
    assert [t["type"] for t in changes["transactions"]] == ["BUY", "DEPOSIT"]  # newest first
    assert changes["holdings"][0]["imported_units"] == pytest.approx(10)
    assert changes["cash_after_gbp"] == pytest.approx(250)

    response = client.post(f"/api/trading212/links/{account.id}/accept")
    assert response.status_code == 200 and response.json()["status"] == "synced"
    assert client.get("/api/trading212/changes").json() == []
    assert client.post(f"/api/trading212/links/{account.id}/accept").status_code == 409


def test_an_already_recorded_share_transfer_does_not_hold_later_syncs(db: Session, fake_provider):
    """Issue #36: the history read overlaps what's recorded, so an old transfer kept being counted."""
    account = _isa(db)
    _instrument(db)
    client = FakeClient(
        orders=[_order(1, "VUSAl_EQ", "BUY", 50, 0, 2500.0, "2026-02-02T09:00:00Z", fill_type="FOP")],
        transactions=[_deposit("d1", 1000, "2026-03-01T08:00:00Z")],
    )
    _connect(db, account, client)
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    assert "share transfer" in (link.status_message or "")
    trading212_service.accept(db, account.id, fake_provider)

    client._data["dividends"].insert(0, _dividend("div1", 3.21, "2026-04-20"))
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    assert link.status == "synced" and link.pending_batch_id is None

    client._data["orders"].insert(0, _order(2, "VUSAl_EQ", "BUY", 1, 8000, 80.0, "2026-05-02T09:30:00Z"))
    link = trading212_service.sync_account(db, account.id, fake_provider, _factory(client))
    assert link.status == "needs_review" and link.status_message == "1 new trade"
