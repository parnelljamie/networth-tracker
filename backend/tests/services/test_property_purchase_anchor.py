"""docs/06-imports-future.md: "Property: purchase price at purchase date plus valuations; growth
model fills between them."

A property's purchase date/price are the first point of its history, not just reference data, so
creating (or later correcting) property details writes a `valuation` BalanceEntry at the purchase
date and rebuilds snapshots from there. Without it the Property chart's value line started on the
day the account was created while its mortgage line ran from completion.
"""
from __future__ import annotations

from datetime import date

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    BalanceSource,
    Category,
    GrowthMethod,
    SnapshotSource,
    ValuationMethod,
    Wrapper,
)
from app.models.balances import BalanceEntry
from app.models.people import Person
from app.models.snapshots import AccountSnapshot
from app.schemas.account import (
    AccountCreate,
    GrowthModelIn,
    InitialBalanceIn,
    OwnerShareIn,
    PropertyDetailsIn,
)
from app.services import account_service, snapshot_service, valuation_service

PURCHASE = date(2022, 7, 10)
PURCHASE_PRICE = 450_000.0
TODAY = date(2026, 9, 17)
CURRENT_VALUE = 700_000.0
RATE = 0.005  # 0.5%/yr, the rate on the reported account


@pytest.fixture()
def rebuilds(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, date]]:
    """Capture request_rebuild instead of spawning its background thread (which would open its own
    session against the real DB rather than the in-memory test one)."""
    calls: list[tuple[int, date]] = []
    monkeypatch.setattr(
        snapshot_service,
        "request_rebuild",
        lambda account_id, from_date: calls.append((account_id, from_date)),
    )
    return calls


def _person(db: Session) -> Person:
    person = Person(name="James")
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _property_payload(
    owner_id: int,
    *,
    purchase_date: date | None = PURCHASE,
    purchase_price: float | None = PURCHASE_PRICE,
    initial_balance: InitialBalanceIn | None = None,
) -> AccountCreate:
    return AccountCreate(
        name="Home",
        category=Category.property,
        wrapper=Wrapper.none,
        valuation_method=ValuationMethod.model,
        owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
        growth_model=GrowthModelIn(annual_rate=RATE, method=GrowthMethod.compound),
        property=PropertyDetailsIn(
            purchase_date=purchase_date, purchase_price_gbp=purchase_price
        ),
        initial_balance=initial_balance,
    )


def _entries(db: Session, account_id: int) -> list[BalanceEntry]:
    return list(
        db.scalars(
            select(BalanceEntry)
            .where(BalanceEntry.account_id == account_id)
            .order_by(BalanceEntry.date)
        ).all()
    )


# ---------------------------------------------------------------------------
# create_account
# ---------------------------------------------------------------------------


def test_purchase_price_becomes_a_valuation_entry_at_the_purchase_date(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(db, _property_payload(james.id))

    entries = _entries(db, account.id)
    assert [(e.date, e.balance_gbp, e.source) for e in entries] == [
        (PURCHASE, PURCHASE_PRICE, BalanceSource.valuation)
    ]
    assert rebuilds == [(account.id, PURCHASE)]


def test_purchase_and_current_value_give_two_anchors_and_rebuild_from_the_earlier(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            initial_balance=InitialBalanceIn(
                date=TODAY, balance_gbp=CURRENT_VALUE, source=BalanceSource.valuation
            ),
        ),
    )

    entries = _entries(db, account.id)
    assert [(e.date, e.balance_gbp) for e in entries] == [
        (PURCHASE, PURCHASE_PRICE),
        (TODAY, CURRENT_VALUE),
    ]
    # The purchase, not the current valuation, is where history starts.
    assert rebuilds == [(account.id, PURCHASE)]


def test_value_runs_in_a_straight_line_between_the_two_valuations(db: Session, rebuilds):
    """The owner's rule: "from purchase price to an update valuation, just draw a straight line
    between them" — no compounding, and so no vertical step where the curve met the newer
    valuation. The growth rate is for the future only."""
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            initial_balance=InitialBalanceIn(
                date=TODAY, balance_gbp=CURRENT_VALUE, source=BalanceSource.valuation
            ),
        ),
    )
    db.refresh(account)

    def value_on(on: date) -> float:
        return valuation_service.value_account(db, account, on, live=False).value_gbp

    assert value_on(PURCHASE) == pytest.approx(PURCHASE_PRICE)
    assert value_on(TODAY) == pytest.approx(CURRENT_VALUE)

    # Halfway between the two dates sits halfway between the two figures (~£575,000).
    span = (TODAY - PURCHASE).days
    midpoint = PURCHASE + (TODAY - PURCHASE) / 2
    assert value_on(midpoint) == pytest.approx((PURCHASE_PRICE + CURRENT_VALUE) / 2, abs=50.0)

    # Every intermediate day is on that same line, not on a 0.5%/yr curve.
    on = date(2024, 1, 1)
    expected = PURCHASE_PRICE + (CURRENT_VALUE - PURCHASE_PRICE) * ((on - PURCHASE).days / span)
    assert value_on(on) == pytest.approx(expected, abs=1.0)
    assert expected > PURCHASE_PRICE * (1 + RATE) ** 1.5  # clearly not the compound curve


def test_after_the_last_valuation_the_growth_model_takes_over(db: Session, rebuilds):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            initial_balance=InitialBalanceIn(
                date=TODAY, balance_gbp=CURRENT_VALUE, source=BalanceSource.valuation
            ),
        ),
    )
    db.refresh(account)

    two_years_on = date(2028, 9, 17)
    expected = CURRENT_VALUE * (1 + RATE) ** 2
    assert valuation_service.value_account(db, account, two_years_on, live=False).value_gbp == (
        pytest.approx(expected, abs=5.0)
    )


def test_before_the_first_valuation_there_is_no_value(db: Session, rebuilds):
    james = _person(db)
    account = account_service.create_account(db, _property_payload(james.id))
    db.refresh(account)

    earlier = valuation_service.value_account(db, account, date(2022, 1, 1), live=False)
    assert earlier.value_gbp == 0.0


def test_an_initial_balance_on_the_purchase_date_is_left_as_the_owner_entered_it(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            initial_balance=InitialBalanceIn(
                date=PURCHASE, balance_gbp=460_000.0, source=BalanceSource.manual
            ),
        ),
    )

    entries = _entries(db, account.id)
    assert [(e.date, e.balance_gbp, e.source) for e in entries] == [
        (PURCHASE, 460_000.0, BalanceSource.manual)
    ]


def test_property_without_a_purchase_price_is_unchanged(db: Session, rebuilds: list[tuple[int, date]]):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            purchase_price=None,
            initial_balance=InitialBalanceIn(date=TODAY, balance_gbp=CURRENT_VALUE),
        ),
    )

    assert [e.date for e in _entries(db, account.id)] == [TODAY]
    assert rebuilds == [(account.id, TODAY)]


# ---------------------------------------------------------------------------
# upsert_property_details — the repair path for accounts created before the fix
# ---------------------------------------------------------------------------


def test_setting_a_purchase_later_backfills_the_anchor_and_rebuilds_from_it(
    db: Session, rebuilds: list[tuple[int, date]]
):
    """The shape of the owner's existing "Home": created with only a current value, corrected
    afterwards through PUT /api/accounts/{id}/property."""
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            purchase_date=None,
            purchase_price=None,
            initial_balance=InitialBalanceIn(date=TODAY, balance_gbp=CURRENT_VALUE),
        ),
    )
    rebuilds.clear()

    account_service.upsert_property_details(
        db,
        account,
        PropertyDetailsIn(purchase_date=PURCHASE, purchase_price_gbp=PURCHASE_PRICE),
    )

    entries = _entries(db, account.id)
    assert [(e.date, e.balance_gbp, e.source) for e in entries] == [
        (PURCHASE, PURCHASE_PRICE, BalanceSource.valuation),
        (TODAY, CURRENT_VALUE, BalanceSource.manual),
    ]
    assert rebuilds == [(account.id, PURCHASE)]


def test_moving_the_purchase_date_moves_our_anchor_rather_than_leaving_a_ghost(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(db, _property_payload(james.id))
    rebuilds.clear()

    corrected = date(2022, 8, 1)
    account_service.upsert_property_details(
        db,
        account,
        PropertyDetailsIn(purchase_date=corrected, purchase_price_gbp=PURCHASE_PRICE),
    )

    assert [(e.date, e.balance_gbp) for e in _entries(db, account.id)] == [
        (corrected, PURCHASE_PRICE)
    ]
    # Rebuild starts at the earlier of the two so the vacated days are recomputed too.
    assert rebuilds == [(account.id, PURCHASE)]


def test_correcting_only_the_purchase_price_re_prices_our_anchor_in_place(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(db, _property_payload(james.id))
    rebuilds.clear()

    account_service.upsert_property_details(
        db, account, PropertyDetailsIn(purchase_date=PURCHASE, purchase_price_gbp=455_000.0)
    )

    assert [(e.date, e.balance_gbp) for e in _entries(db, account.id)] == [(PURCHASE, 455_000.0)]
    assert rebuilds == [(account.id, PURCHASE)]


def test_a_manual_entry_on_the_purchase_date_is_never_overwritten(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            purchase_date=None,
            purchase_price=None,
            initial_balance=InitialBalanceIn(
                date=PURCHASE, balance_gbp=448_000.0, source=BalanceSource.manual
            ),
        ),
    )
    rebuilds.clear()

    account_service.upsert_property_details(
        db,
        account,
        PropertyDetailsIn(purchase_date=PURCHASE, purchase_price_gbp=PURCHASE_PRICE),
    )

    assert [(e.date, e.balance_gbp, e.source) for e in _entries(db, account.id)] == [
        (PURCHASE, 448_000.0, BalanceSource.manual)
    ]
    assert rebuilds == []


def test_re_saving_the_same_details_backfills_a_missing_anchor(
    db: Session, rebuilds: list[tuple[int, date]]
):
    """The repair path for the owner's real "Home": it already records the right purchase date and
    price (they predate this fix) but has no BalanceEntry for them, so re-saving the *unchanged*
    details through PUT /api/accounts/{id}/property must still create the anchor. Hence there is
    no "details unchanged, nothing to do" short-circuit."""
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            purchase_date=None,
            purchase_price=None,
            initial_balance=InitialBalanceIn(date=TODAY, balance_gbp=CURRENT_VALUE),
        ),
    )
    # Reproduce the pre-fix shape: details recorded, anchor entry missing.
    account.property_details.purchase_date = PURCHASE
    account.property_details.purchase_price_gbp = PURCHASE_PRICE
    db.commit()
    rebuilds.clear()

    account_service.upsert_property_details(
        db,
        account,
        PropertyDetailsIn(purchase_date=PURCHASE, purchase_price_gbp=PURCHASE_PRICE),
    )

    assert [(e.date, e.balance_gbp, e.source) for e in _entries(db, account.id)] == [
        (PURCHASE, PURCHASE_PRICE, BalanceSource.valuation),
        (TODAY, CURRENT_VALUE, BalanceSource.manual),
    ]
    assert rebuilds == [(account.id, PURCHASE)]


def test_re_saving_unchanged_property_details_with_the_anchor_present_does_nothing(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(db, _property_payload(james.id))
    rebuilds.clear()

    account_service.upsert_property_details(
        db,
        account,
        PropertyDetailsIn(purchase_date=PURCHASE, purchase_price_gbp=PURCHASE_PRICE),
    )

    assert len(_entries(db, account.id)) == 1
    assert rebuilds == []


# ---------------------------------------------------------------------------
# Snapshots — the end-to-end symptom the owner reported
# ---------------------------------------------------------------------------


@freeze_time("2026-09-17")
def test_snapshots_run_from_the_purchase_date(db: Session, rebuilds: list[tuple[int, date]]):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            initial_balance=InitialBalanceIn(
                date=TODAY, balance_gbp=CURRENT_VALUE, source=BalanceSource.valuation
            ),
        ),
    )
    snapshot_service.rebuild(db, account.id, PURCHASE)

    rows = snapshot_service.account_history(db, account.id, date(2000, 1, 1), TODAY)
    assert rows[0].date == PURCHASE  # nothing before the purchase, not a flat £0 run
    assert rows[0].value_gbp == pytest.approx(PURCHASE_PRICE)
    assert rows[-1].date == TODAY
    assert rows[-1].value_gbp == pytest.approx(CURRENT_VALUE)
    assert rows[1].value_gbp > rows[0].value_gbp  # the growth model fills between the anchors


@freeze_time("2026-09-17")
def test_rebuild_drops_zero_valued_days_from_before_the_account_had_any_value(
    db: Session, rebuilds: list[tuple[int, date]]
):
    """catch_up backfills every account across the whole snapshot range, so an account added later
    carries zero-valued rows reaching back to the start of household history — on the Property
    chart that was a flat £0 line before the purchase."""
    james = _person(db)
    account = account_service.create_account(db, _property_payload(james.id))
    stale = date(2021, 4, 6)
    db.add(
        AccountSnapshot(
            account_id=account.id,
            date=stale,
            value_gbp=0.0,
            is_estimated=True,
            source=SnapshotSource.backfill,
        )
    )
    db.commit()

    snapshot_service.rebuild(db, account.id, PURCHASE)

    rows = snapshot_service.account_history(db, account.id, date(2000, 1, 1), TODAY)
    assert rows[0].date == PURCHASE


@freeze_time("2026-09-17")
def test_changing_the_growth_rate_rebuilds_from_the_earliest_anchor(
    db: Session, rebuilds: list[tuple[int, date]]
):
    james = _person(db)
    account = account_service.create_account(
        db,
        _property_payload(
            james.id,
            initial_balance=InitialBalanceIn(date=TODAY, balance_gbp=CURRENT_VALUE),
        ),
    )
    rebuilds.clear()

    account_service.upsert_growth_model(
        db, account, GrowthModelIn(annual_rate=0.02, method=GrowthMethod.compound)
    )

    assert rebuilds == [(account.id, PURCHASE)]
