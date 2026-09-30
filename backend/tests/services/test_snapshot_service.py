from __future__ import annotations

from datetime import date

import pytest
from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import BalanceSource, Category, RateType, ValuationMethod, Wrapper
from app.models.balances import BalanceEntry
from app.models.people import Person
from app.models.snapshots import AccountSnapshot
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.loan import LoanDetailsCreate, RatePeriodIn
from app.services import account_service, ledger_service, snapshot_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _cash_account(db: Session, owner_id: int, on: date, balance: float, name: str = "Cash"):
    return account_service.create_account(
        db,
        AccountCreate(
            name=name,
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            initial_balance=InitialBalanceIn(date=on, balance_gbp=balance),
        ),
    )


def test_create_account_with_initial_balance_triggers_a_snapshot_rebuild(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    calls: list[tuple[int, date]] = []
    monkeypatch.setattr(
        snapshot_service, "request_rebuild", lambda account_id, from_date: calls.append((account_id, from_date))
    )
    james = _person(db)
    account = _cash_account(db, james.id, date(2026, 7, 1), 1000.0)

    assert calls == [(account.id, date(2026, 7, 1))]


def test_create_amortising_loan_account_triggers_a_rebuild_from_its_start_date(
    db: Session, monkeypatch: pytest.MonkeyPatch
):
    """Property page's "Add mortgage" flow (or any amortising account creation): unlike
    balance/model accounts there's no initial_balance to anchor a rebuild from, so without this
    the new loan would have zero AccountSnapshot rows until the next nightly catch_up — leaving
    the Property chart with nothing to plot for "history solid" (docs/05-ui.md)."""
    calls: list[tuple[int, date]] = []
    monkeypatch.setattr(
        snapshot_service, "request_rebuild", lambda account_id, from_date: calls.append((account_id, from_date))
    )
    james = _person(db)
    start = date(2024, 9, 16)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Mortgage",
            category=Category.mortgage,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.amortising,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
            loan=LoanDetailsCreate(
                original_amount_gbp=280000.0,
                start_date=start,
                maturity_date=date(2049, 9, 16),
                fallback_rate=0.045,
                rate_periods=[
                    RatePeriodIn(start_date=start, end_date=None, annual_rate=0.045, rate_type=RateType.fixed)
                ],
            ),
        ),
    )

    assert calls == [(account.id, start)]


def test_take_writes_a_snapshot_for_accounts_with_data(db: Session):
    james = _person(db)
    account = _cash_account(db, james.id, date(2026, 9, 1), 100.0)

    snapshot_service.take(db, date(2026, 9, 1))

    row = db.get(AccountSnapshot, (account.id, date(2026, 9, 1)))
    assert row is not None
    assert row.value_gbp == 100.0
    assert row.source.value == "daily"


def test_take_skips_accounts_with_no_data(db: Session):
    james = _person(db)
    account = account_service.create_account(
        db,
        AccountCreate(
            name="Empty",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    snapshot_service.take(db, date(2026, 9, 1))
    assert db.get(AccountSnapshot, (account.id, date(2026, 9, 1))) is None


def test_catch_up_backfills_missing_calendar_days(db: Session):
    james = _person(db)
    account = _cash_account(db, james.id, date(2026, 9, 1), 100.0)
    db.add(AccountSnapshot(account_id=account.id, date=date(2026, 9, 10), value_gbp=100.0, source="daily"))
    db.commit()

    with freeze_time("2026-09-14 09:00:00"):
        snapshot_service.catch_up(db)

    for d in (11, 12, 13):
        row = db.get(AccountSnapshot, (account.id, date(2026, 9, d)))
        assert row is not None, f"missing snapshot for day {d}"
        assert row.source.value == "backfill"
    assert db.get(AccountSnapshot, (account.id, date(2026, 9, 14))) is not None


def test_catch_up_is_not_fooled_by_one_account_already_snapshotted_today(db: Session):
    # Regression: catch_up keyed off the newest snapshot of any account, so a single account
    # added or edited today made it skip every other account's missing days.
    james = _person(db)
    behind = _cash_account(db, james.id, date(2026, 9, 1), 100.0, name="Behind")
    current = _cash_account(db, james.id, date(2026, 9, 1), 50.0, name="Current")
    db.query(AccountSnapshot).delete()
    db.add(AccountSnapshot(account_id=behind.id, date=date(2026, 9, 10), value_gbp=100.0, source="daily"))
    db.add(AccountSnapshot(account_id=current.id, date=date(2026, 9, 14), value_gbp=50.0, source="rebuild"))
    db.commit()

    with freeze_time("2026-09-14 09:00:00"):
        snapshot_service.catch_up(db)

    for d in (11, 12, 13, 14):
        assert db.get(AccountSnapshot, (behind.id, date(2026, 9, d))) is not None, f"missing day {d}"


def test_rebuild_recomputes_snapshots_from_a_backdated_balance(db: Session):
    james = _person(db)
    account = _cash_account(db, james.id, date(2026, 1, 1), 100.0)
    snapshot_service.take(db, date(2026, 3, 1))
    assert db.get(AccountSnapshot, (account.id, date(2026, 3, 1))).value_gbp == 100.0

    # A statement dated 60 days ago corrects the balance.
    db.add(BalanceEntry(account_id=account.id, date=date(2026, 1, 15), balance_gbp=250.0, source=BalanceSource.statement))
    db.commit()
    snapshot_service.rebuild(db, account.id, date(2026, 1, 15))

    row = db.get(AccountSnapshot, (account.id, date(2026, 3, 1)))
    assert row.value_gbp == 250.0
    assert row.source.value == "rebuild"


def test_history_aggregates_by_person_using_shares(db: Session):
    james = _person(db, "James")
    sam = _person(db, "Sam")
    joint = account_service.create_account(
        db,
        AccountCreate(
            name="Joint",
            category=Category.cash,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.balance,
            owners=[OwnerShareIn(person_id=james.id, share=0.5), OwnerShareIn(person_id=sam.id, share=0.5)],
            initial_balance=InitialBalanceIn(date=date(2026, 9, 1), balance_gbp=2000.0),
        ),
    )
    snapshot_service.take(db, date(2026, 9, 1))

    result = snapshot_service.history(
        db, person_id=None, date_from=date(2026, 9, 1), date_to=date(2026, 9, 1), group_by="person"
    )
    values_by_key = {s.key: s.values[0] for s in result.series}
    assert values_by_key[str(james.id)] == 1000.0
    assert values_by_key[str(sam.id)] == 1000.0
    assert result.total == [2000.0]
    assert joint.id  # keep the linter happy about the unused create result


def test_total_on_or_before_uses_the_nearest_snapshot(db: Session):
    james = _person(db)
    account = _cash_account(db, james.id, date(2026, 1, 1), 100.0)
    snapshot_service.take(db, date(2026, 1, 1))
    snapshot_service.take(db, date(2026, 6, 1))
    db.query(AccountSnapshot).filter(
        AccountSnapshot.account_id == account.id, AccountSnapshot.date == date(2026, 6, 1)
    ).update({"value_gbp": 150.0})
    db.commit()

    assert snapshot_service.total_on_or_before(db, {james.id}, date(2026, 3, 1)) == 100.0
    assert snapshot_service.total_on_or_before(db, {james.id}, date(2026, 12, 31)) == 150.0
    assert snapshot_service.total_on_or_before(db, {james.id}, date(2025, 1, 1)) is None


def test_daily_snapshot_includes_a_mortgage_valued_from_its_terms_alone(db: Session):
    # Regression: an amortising loan with no balance entries was skipped by take(), so the
    # overview history showed the mortgage as £0 on today's date.
    james = _person(db)
    with freeze_time("2026-09-18"):
        account = account_service.create_account(
            db,
            AccountCreate(
                name="Mortgage",
                category=Category.mortgage,
                wrapper=Wrapper.none,
                valuation_method=ValuationMethod.amortising,
                owners=[OwnerShareIn(person_id=james.id, share=1.0)],
                loan=LoanDetailsCreate(
                    original_amount_gbp=200000.0,
                    start_date=date(2022, 7, 17),
                    maturity_date=date(2052, 7, 17),
                    fallback_rate=0.021,
                    rate_periods=[
                        RatePeriodIn(
                            start_date=date(2022, 7, 17), end_date=None, annual_rate=0.021,
                            rate_type=RateType.fixed,
                        )
                    ],
                ),
            ),
        )
        db.query(AccountSnapshot).delete()
        db.commit()

        snapshot_service.take(db, date(2026, 9, 18))

    row = db.get(AccountSnapshot, (account.id, date(2026, 9, 18)))
    assert row is not None
    assert row.value_gbp < 0


def test_history_carries_accounts_forward_on_days_they_have_no_snapshot_yet(db: Session):
    # Regression: an account added this morning has a snapshot for today while the rest only get
    # theirs from tonight's job; today must not count those others as £0.
    james = _person(db)
    with freeze_time("2026-09-19"):
        old = _cash_account(db, james.id, date(2026, 9, 17), 1000.0, name="Old")
        new = _cash_account(db, james.id, date(2026, 9, 19), 500.0, name="New")
        db.query(AccountSnapshot).delete()
        db.add_all(
            [
                AccountSnapshot(account_id=old.id, date=date(2026, 9, 17), value_gbp=1000.0),
                AccountSnapshot(account_id=old.id, date=date(2026, 9, 18), value_gbp=1000.0),
                AccountSnapshot(account_id=new.id, date=date(2026, 9, 19), value_gbp=500.0),
            ]
        )
        db.commit()

        result = snapshot_service.history(
            db, person_id=None, date_from=date(2026, 9, 17), date_to=date(2026, 9, 19)
        )

    assert result.dates == [date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 19)]
    assert result.total == [1000.0, 1000.0, 1500.0]


def test_history_includes_today_live_before_the_nightly_snapshot_runs(db: Session):
    # Regression: the app left running overnight has no row for today until 22:15, so the chart
    # stopped at yesterday all day even though balances and prices were current.
    james = _person(db)
    with freeze_time("2026-09-20"):
        one = _cash_account(db, james.id, date(2026, 9, 18), 1000.0, name="One")
        two = _cash_account(db, james.id, date(2026, 9, 18), 500.0, name="Two")
        db.query(AccountSnapshot).delete()
        db.add_all(
            [
                AccountSnapshot(account_id=one.id, date=date(2026, 9, 18), value_gbp=1000.0),
                AccountSnapshot(account_id=one.id, date=date(2026, 9, 19), value_gbp=1000.0),
                AccountSnapshot(account_id=two.id, date=date(2026, 9, 18), value_gbp=500.0),
                AccountSnapshot(account_id=two.id, date=date(2026, 9, 19), value_gbp=500.0),
            ]
        )
        db.commit()

        result = snapshot_service.history(
            db, person_id=None, date_from=date(2026, 9, 18), date_to=date(2026, 9, 20)
        )

    assert result.dates == [date(2026, 9, 18), date(2026, 9, 19), date(2026, 9, 20)]
    assert result.total == [1500.0, 1500.0, 1500.0]
    # The provisional point is not persisted; only the nightly job writes snapshots.
    assert db.get(AccountSnapshot, (one.id, date(2026, 9, 20))) is None


def test_history_does_not_invent_a_point_past_the_requested_end(db: Session):
    james = _person(db)
    with freeze_time("2026-09-20"):
        account = _cash_account(db, james.id, date(2026, 9, 18), 1000.0)
        db.query(AccountSnapshot).delete()
        db.add(AccountSnapshot(account_id=account.id, date=date(2026, 9, 18), value_gbp=1000.0))
        db.commit()

        result = snapshot_service.history(
            db, person_id=None, date_from=date(2026, 9, 17), date_to=date(2026, 9, 19)
        )

    assert result.dates == [date(2026, 9, 18)]


def _holdings_account_with_history(db: Session):
    """A holdings account whose ledger spans several days, priced from a manual instrument."""
    from app.core.enums import PriceSource, TxnType
    from app.models.instruments import Instrument
    from app.models.transactions import Transaction

    james = _person(db, "Holder")
    account = account_service.create_account(
        db,
        AccountCreate(
            name="SIPP",
            category=Category.pension,
            wrapper=Wrapper.sipp,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    instrument = Instrument(
        symbol="MANUAL:FUND",
        name="Fund",
        quote_currency="GBP",
        price_source=PriceSource.manual,
        manual_price_gbp=12.0,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)

    db.add_all(
        [
            Transaction(account_id=account.id, date=date(2026, 9, 1), type=TxnType.DEPOSIT, amount_gbp=1000.0),
            Transaction(
                account_id=account.id, date=date(2026, 9, 3), type=TxnType.BUY,
                instrument_id=instrument.id, units=50.0, amount_gbp=-500.0, cost_basis_gbp=500.0,
            ),
            Transaction(account_id=account.id, date=date(2026, 9, 6), type=TxnType.DEPOSIT, amount_gbp=250.0),
            Transaction(
                account_id=account.id, date=date(2026, 9, 8), type=TxnType.SELL,
                instrument_id=instrument.id, units=20.0, amount_gbp=240.0,
            ),
        ]
    )
    db.commit()
    ledger_service.rebuild_positions(db, account.id)
    db.commit()
    return account


def test_rebuild_of_a_holdings_account_matches_the_per_day_valuation(db: Session):
    """The fast path replays the ledger once for the whole range (docs/03-domain-logic.md §4)
    instead of once per day; it must still produce exactly what value_account would have."""
    from app.services import valuation_service

    account = _holdings_account_with_history(db)
    start, end = date(2026, 9, 1), date(2026, 9, 10)
    with freeze_time("2026-09-10"):
        expected = {
            d: valuation_service.value_account(db, account, d, live=(d == end))
            for d in snapshot_service._all_dates_in_range(start, end)
        }
        snapshot_service.rebuild(db, account.id, start)

        rows = snapshot_service.account_history(db, account.id, start, end)

    assert [r.date for r in rows] == sorted(expected)
    for row in rows:
        want = expected[row.date]
        assert row.value_gbp == want.value_gbp, row.date
        assert row.cost_basis_gbp == pytest.approx(want.cost_basis_gbp), row.date
        assert row.is_estimated == want.is_estimated, row.date
        assert row.source.value == "rebuild"
    # Non-trivial history, not a run of zeroes that would match by accident.
    assert rows[0].value_gbp == 1000.0
    assert rows[-1].value_gbp > 1000.0


def test_rebuild_of_a_holdings_account_drops_days_before_its_first_transaction(db: Session):
    account = _holdings_account_with_history(db)
    db.add(AccountSnapshot(account_id=account.id, date=date(2026, 8, 1), value_gbp=0.0, source="backfill"))
    db.commit()

    with freeze_time("2026-09-10"):
        snapshot_service.rebuild(db, account.id, date(2026, 8, 1))

    assert db.get(AccountSnapshot, (account.id, date(2026, 8, 1))) is None
    assert db.get(AccountSnapshot, (account.id, date(2026, 9, 1))) is not None


def test_holdings_snapshots_carry_the_ledger_s_net_contributions(db: Session):
    """Regression: `value_account` hardcoded `net_contributions_gbp=None`, so every snapshot
    written through `_write_snapshot` (the daily `take` and the rebuild's "today" row) left the
    column NULL even though `engine.ledger` accumulates the figure during replay."""
    account = _holdings_account_with_history(db)
    start, end = date(2026, 9, 1), date(2026, 9, 10)
    with freeze_time("2026-09-10"):
        snapshot_service.rebuild(db, account.id, start)
        rows = snapshot_service.account_history(db, account.id, start, end)

    by_date = {row.date: row.net_contributions_gbp for row in rows}
    # £1,000 deposited on the 1st, another £250 on the 6th; buys and sells move cash but are not
    # contributions, so the running total only steps on deposit days.
    assert by_date[date(2026, 9, 1)] == 1000.0
    assert by_date[date(2026, 9, 5)] == 1000.0
    assert by_date[date(2026, 9, 6)] == 1250.0
    assert by_date[date(2026, 9, 8)] == 1250.0
    # Today goes through the live path (positions cache), which has to replay for this figure.
    assert by_date[end] == 1250.0


def test_net_contributions_stays_none_for_non_holdings_accounts(db: Session):
    james = _person(db, "Saver")
    account = _cash_account(db, james.id, date(2026, 9, 1), 5000.0)

    with freeze_time("2026-09-10"):
        snapshot_service.take(db, date(2026, 9, 10))
        row = db.get(AccountSnapshot, (account.id, date(2026, 9, 10)))

    assert row is not None
    assert row.value_gbp == 5000.0
    assert row.net_contributions_gbp is None


def test_net_contributions_is_opt_in_on_value_account(db: Session):
    """The live holdings path pays a full ledger replay for it, so callers that only want a value
    (the accounts list, projections, insights) must not be charged for it."""
    from app.services import valuation_service

    account = _holdings_account_with_history(db)
    on = date(2026, 9, 10)
    with freeze_time("2026-09-10"):
        for live in (True, False):
            assert valuation_service.value_account(db, account, on, live=live).net_contributions_gbp is None
            opted_in = valuation_service.value_account(
                db, account, on, live=live, with_net_contributions=True
            )
            assert opted_in.net_contributions_gbp == 1250.0


def _yahoo_holdings_account(db: Session):
    """10 units of a Yahoo-priced ETF last priced at a 100.00 close on Friday 18 Sep."""
    from app.core.enums import PriceSource, TxnType
    from app.models.instruments import Instrument
    from app.models.prices import InstrumentPrice
    from app.models.transactions import Transaction

    james = _person(db, "Holder")
    account = account_service.create_account(
        db,
        AccountCreate(
            name="ISA",
            category=Category.investment,
            wrapper=Wrapper.isa,
            valuation_method=ValuationMethod.holdings,
            owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        ),
    )
    instrument = Instrument(
        symbol="VUAG.L", name="ETF", quote_currency="GBP", price_source=PriceSource.yahoo
    )
    db.add(instrument)
    db.commit()
    db.add_all(
        [
            InstrumentPrice(
                instrument_id=instrument.id, date=date(2026, 9, 18), close_native=100.0,
                close_gbp=100.0, source=PriceSource.yahoo,
            ),
            Transaction(account_id=account.id, date=date(2026, 9, 1), type=TxnType.DEPOSIT, amount_gbp=1000.0),
            Transaction(
                account_id=account.id, date=date(2026, 9, 1), type=TxnType.BUY,
                instrument_id=instrument.id, units=10.0, amount_gbp=-1000.0, cost_basis_gbp=1000.0,
            ),
        ]
    )
    db.commit()
    ledger_service.rebuild_positions(db, account.id)
    db.commit()
    return account


def test_price_refresh_revalues_the_snapshot_already_taken_today(db: Session):
    """Regression #28: startup wrote today's row from a days-old cached quote, and the refresh
    minutes later never replaced it, so the chart showed a drop that wasn't there."""
    from tests.fakes import FakeProvider

    account = _yahoo_holdings_account(db)
    provider = FakeProvider()
    provider.set_quote("VUAG.L", last=112.0, prev_close=110.0, bar_date=date(2026, 9, 22))

    with freeze_time("2026-09-22 20:45:00"):
        snapshot_service.take(db, date(2026, 9, 22))
        assert db.get(AccountSnapshot, (account.id, date(2026, 9, 22))).value_gbp == 1000.0

        snapshot_service.refresh_quotes(db, provider, force=True)

    row = db.get(AccountSnapshot, (account.id, date(2026, 9, 22)))
    db.refresh(row)
    assert row.value_gbp == 1120.0


def test_price_refresh_does_not_create_today_s_snapshot(db: Session):
    """Creating today's rows here would make catch_up think the missing days were done."""
    from tests.fakes import FakeProvider

    account = _yahoo_holdings_account(db)
    db.query(AccountSnapshot).delete()
    db.commit()
    provider = FakeProvider()
    provider.set_quote("VUAG.L", last=112.0, prev_close=110.0, bar_date=date(2026, 9, 22))

    with freeze_time("2026-09-22 20:45:00"):
        result = snapshot_service.refresh_quotes(db, provider, force=True)

    assert result.refreshed == 1
    assert db.get(AccountSnapshot, (account.id, date(2026, 9, 22))) is None
