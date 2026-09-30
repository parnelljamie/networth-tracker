from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Category, PlanKind, PriceSource, ValuationMethod
from app.engine import amortisation, growth, ledger
from app.engine import recurring as recurring_engine
from app.models.accounts import Account
from app.models.balances import BalanceEntry
from app.models.instruments import Instrument
from app.models.positions import Position
from app.models.recurring import RecurringPlan
from app.services import ledger_service, price_service, settings_service

LIABILITY_CATEGORIES = {
    Category.mortgage,
    Category.loan,
    Category.credit_card,
    Category.other_liability,
}


@dataclass
class Valuation:
    value_gbp: float
    cost_basis_gbp: float | None
    net_contributions_gbp: float | None
    day_change_gbp: float | None
    is_estimated: bool
    detail: str | None


def latest_balance_entry(db: Session, account_id: int, on: date) -> BalanceEntry | None:
    return db.scalars(
        select(BalanceEntry)
        .where(BalanceEntry.account_id == account_id, BalanceEntry.date <= on)
        .order_by(BalanceEntry.date.desc())
        .limit(1)
    ).first()


def next_balance_entry(db: Session, account_id: int, after: date) -> BalanceEntry | None:
    """The first entry strictly after `after` — the far end of an interpolated segment."""
    return db.scalars(
        select(BalanceEntry)
        .where(BalanceEntry.account_id == account_id, BalanceEntry.date > after)
        .order_by(BalanceEntry.date)
        .limit(1)
    ).first()


def earliest_balance_entry(db: Session, account_id: int) -> BalanceEntry | None:
    """The account's first anchor. Changing a growth model or a property's purchase price moves
    every modelled day from that anchor onwards, so rebuilds start here, not at the latest entry."""
    return db.scalars(
        select(BalanceEntry)
        .where(BalanceEntry.account_id == account_id)
        .order_by(BalanceEntry.date)
        .limit(1)
    ).first()


def value_account(
    db: Session,
    account: Account,
    on: date,
    live: bool,
    *,
    with_net_contributions: bool = False,
) -> Valuation:
    """Value one account on `on`.

    `with_net_contributions` is opt-in because on a live holdings valuation it costs a full
    ledger replay (the live path otherwise reads only the positions cache), and the only caller
    that needs the figure is the snapshot writer. It stays None for non-holdings accounts.
    """
    cost_basis_gbp: float | None = None
    net_contributions_gbp: float | None = None
    day_change_gbp: float | None = None

    if account.valuation_method == ValuationMethod.balance:
        raw, is_estimated, detail = _value_balance(db, account, on)
    elif account.valuation_method == ValuationMethod.model:
        raw, is_estimated, detail = _value_model(db, account, on)
    elif account.valuation_method == ValuationMethod.holdings:
        raw, is_estimated, detail, cost_basis_gbp, day_change_gbp, net_contributions_gbp = (
            _value_holdings(db, account, on, live, with_net_contributions)
        )
    elif account.valuation_method == ValuationMethod.amortising:
        raw, is_estimated, detail = _value_amortising(db, account, on)
    elif account.valuation_method == ValuationMethod.defined_benefit:
        raw, is_estimated, detail = _value_defined_benefit(db, account, on)
    else:
        raise NotImplementedError(
            f"{account.valuation_method.value} accounts are not supported until a later phase"
        )

    sign = -1.0 if account.category in LIABILITY_CATEGORIES else 1.0
    return Valuation(
        value_gbp=round(raw * sign, 2),
        cost_basis_gbp=cost_basis_gbp,
        net_contributions_gbp=(
            round(net_contributions_gbp, 2) if net_contributions_gbp is not None else None
        ),
        day_change_gbp=round(day_change_gbp * sign, 2) if day_change_gbp is not None else None,
        is_estimated=is_estimated,
        detail=detail,
    )


def _value_defined_benefit(db: Session, account: Account, on: date) -> tuple[float, bool, str | None]:
    """Capitalised value of a DB pension: yearly pension x factor (+ lump sum). Always an
    estimate: there is no pot, only a promised income."""
    from app.services import db_pension_service

    if account.db_pension_details is None:
        return 0.0, True, None
    return db_pension_service.value_on(db, account, on), True, None


def _format_day_month(d: date) -> str:
    """Windows strftime has no %-d; format "1 Sep" portably."""
    return f"{d.day} {d.strftime('%b')}"


def _value_balance(db: Session, account: Account, on: date) -> tuple[float, bool, str | None]:
    """docs/03-domain-logic.md §1 "balance": latest entry, plus expected contributions from
    active contribution/withdrawal plans since that entry (roll-forward)."""
    entry = latest_balance_entry(db, account.id, on)
    if entry is None:
        return 0.0, True, None
    if entry.date >= on:
        return entry.balance_gbp, False, None

    from app.services import recurring_service

    plans = list(
        db.scalars(
            select(RecurringPlan).where(
                RecurringPlan.account_id == account.id,
                RecurringPlan.is_active.is_(True),
                RecurringPlan.kind.in_([PlanKind.contribution, PlanKind.withdrawal]),
            )
        ).all()
    )
    added = 0.0
    for plan in plans:
        engine_plan = recurring_service.to_engine(plan)
        for _d, amount in recurring_engine.occurrences(engine_plan, entry.date + timedelta(days=1), on):
            added += amount if plan.kind == PlanKind.contribution else -amount

    if abs(added) <= 0.005:
        return entry.balance_gbp, False, None

    detail = (
        f"includes £{added:,.2f} expected contributions since {_format_day_month(entry.date)}"
        if added > 0
        else f"includes £{-added:,.2f} expected withdrawals since {_format_day_month(entry.date)}"
    )
    return entry.balance_gbp + added, True, detail


def _value_model(db: Session, account: Account, on: date) -> tuple[float, bool, str | None]:
    """docs/03-domain-logic.md §1 "model": between two known valuations the value is a straight
    line between them; after the last one the growth model takes over. The growth rate describes
    the future, not the past — modelling forward from an old valuation and then meeting a newer
    one would put a vertical step in the history chart on the day of the newer valuation.
    """
    entry = latest_balance_entry(db, account.id, on)
    if entry is None:
        return 0.0, True, None  # before the first valuation: nothing to extrapolate back to
    if entry.date == on:
        return entry.balance_gbp, False, None

    later = next_balance_entry(db, account.id, on)
    if later is not None:
        span_days = (later.date - entry.date).days
        elapsed_days = (on - entry.date).days
        fraction = elapsed_days / span_days if span_days else 0.0
        return entry.balance_gbp + (later.balance_gbp - entry.balance_gbp) * fraction, True, None

    gm = account.growth_model
    if gm is None:
        return entry.balance_gbp, True, None
    value = growth.value_on(
        entry.balance_gbp,
        entry.date,
        on,
        gm.annual_rate,
        gm.method,
        gm.floor_value_gbp,
        gm.cap_value_gbp,
    )
    return value, True, None


def _value_amortising(db: Session, account: Account, on: date) -> tuple[float, bool, str | None]:
    """docs/03-domain-logic.md §1 "amortising": anchor from the latest statement/manual balance
    entry on/before `on`, falling back to the loan's original amount at its start date when no
    entry exists yet (docs/03-domain-logic.md §5 "anchor"); amortisation.build_schedule(...) then
    balance_on(rows, on, anchor.balance)."""
    from app.core.errors import DomainError
    from app.services import loan_service

    try:
        anchor = loan_service.get_anchor(db, account)
    except DomainError:
        return 0.0, True, None
    terms = loan_service.terms_for(account)
    actual = loan_service.actual_overpayments(db, account.id)
    rows = amortisation.build_schedule(terms, anchor.balance_gbp, anchor.date, actual, until=on)
    balance = amortisation.balance_on(rows, on, anchor.balance_gbp)
    return balance, bool(rows), None


def _replay(db: Session, account: Account, on: date) -> ledger.LedgerState:
    """Ledger state for a holdings account after every confirmed transaction up to `on`."""
    rows = ledger_service.confirmed_txns(db, account.id)
    return ledger.replay([ledger_service.to_engine_txn(r) for r in rows], as_of=on, strict=False)


def _value_holdings(
    db: Session, account: Account, on: date, live: bool, with_net_contributions: bool = False
) -> tuple[float, bool, str | None, float, float, float | None]:
    """docs/03-domain-logic.md §1 "holdings": today (live) uses the positions cache and
    accounts.cash_balance_gbp; a historical date replays confirmed transactions up to it."""
    is_estimated = False
    cost_basis_gbp = 0.0
    day_change_gbp = 0.0
    net_contributions_gbp: float | None = None

    if live:
        positions = list(
            db.scalars(select(Position).where(Position.account_id == account.id)).all()
        )
        cash = account.cash_balance_gbp
        held = [(p.instrument, p.units, p.cost_basis_gbp) for p in positions]
        if with_net_contributions:
            # The positions cache doesn't carry cumulative flows, so this is the one thing the
            # live path has to replay the ledger for.
            net_contributions_gbp = _replay(db, account, on).net_contributions_gbp
    else:
        state = _replay(db, account, on)
        cash = state.cash_gbp
        if with_net_contributions:
            net_contributions_gbp = state.net_contributions_gbp
        instrument_ids = list(state.held().keys())
        instruments = {
            i.id: i
            for i in db.scalars(select(Instrument).where(Instrument.id.in_(instrument_ids))).all()
        }
        held = [
            (instruments[iid], pos.units, pos.cost_gbp)
            for iid, pos in state.held().items()
            if iid in instruments
        ]

    total = cash
    for instrument, units, position_cost in held:
        result = price_service.price_gbp(db, instrument, on, live)
        total += units * result.price_gbp
        cost_basis_gbp += position_cost
        if result.is_stale:
            is_estimated = True
        day_change_gbp += price_service.day_change_contribution(instrument, units, on, db)

    return total, is_estimated, None, cost_basis_gbp, day_change_gbp, net_contributions_gbp


def modelled_value_gbp(db: Session, account: Account, on: date) -> float | None:
    """Unsigned grown value (same sense as balance_gbp), for the quick-update hint."""
    if account.valuation_method != ValuationMethod.model:
        return None
    entry = latest_balance_entry(db, account.id, on)
    if entry is None:
        return None
    raw, _is_estimated, _detail = _value_model(db, account, on)
    return round(raw, 2)


def scoped_value(value_gbp: float, account: Account, person_ids: set[int]) -> float:
    """value_gbp scaled by the combined share of owners in `person_ids` (household or one person)."""
    share = sum(o.share for o in account.owners if o.person_id in person_ids)
    return round(value_gbp * share, 2)


def days_since_last_entry(db: Session, account: Account, on: date) -> int | None:
    entry = latest_balance_entry(db, account.id, on)
    if entry is None:
        return None
    return (on - entry.date).days


def staleness(db: Session, account: Account, on: date) -> str:
    if account.valuation_method == ValuationMethod.holdings:
        return _holdings_staleness(db, account, on)

    if account.valuation_method not in (ValuationMethod.balance, ValuationMethod.model, ValuationMethod.amortising):
        return "ok"
    days_since = days_since_last_entry(db, account, on)
    if days_since is None:
        return "alert"
    thresholds = settings_service.get(db, "stale_balance_days", {"warn": 35, "alert": 90})
    if days_since >= thresholds["alert"]:
        return "alert"
    if days_since >= thresholds["warn"]:
        return "warn"
    return "ok"


def holdings_price_age_days(db: Session, account: Account, on: date) -> int | None:
    """Age in days of the oldest latest-known price among the account's Yahoo-priced holdings,
    or None when none is priced yet (or nothing is Yahoo-priced)."""
    positions = db.scalars(select(Position).where(Position.account_id == account.id)).all()
    ages: list[int] = []
    for pos in positions:
        if pos.instrument.price_source != PriceSource.yahoo:
            continue
        row = price_service.latest_price_on_or_before(db, pos.instrument.id, on)
        if row is None:
            return None
        ages.append((on - row.date).days)
    return max(ages) if ages else None


def days_since_update(db: Session, account: Account, on: date) -> int | None:
    """What the staleness badge counts: days since the last balance entry, or for holdings the
    age of the oldest held price. None means there is nothing to count from."""
    if account.valuation_method == ValuationMethod.holdings:
        return holdings_price_age_days(db, account, on)
    if account.valuation_method in (ValuationMethod.balance, ValuationMethod.model, ValuationMethod.amortising):
        return days_since_last_entry(db, account, on)
    return None


def _holdings_staleness(db: Session, account: Account, on: date) -> str:
    """docs/04-api.md: warn if any held price is >3 days old (4 over a weekend), alert if >10.

    "Held price" means the latest known close for that instrument (instrument_prices), not the
    live-refresh timestamp — a freshly history-backfilled instrument counts as fresh even before
    its first live refresh_quotes() run.
    """
    positions = list(db.scalars(select(Position).where(Position.account_id == account.id)).all())
    warn_threshold = 4 if on.weekday() == 0 else 3  # Monday accounts for the weekend gap
    worst = "ok"
    for pos in positions:
        instrument = pos.instrument
        if instrument.price_source != PriceSource.yahoo:
            continue
        row = price_service.latest_price_on_or_before(db, instrument.id, on)
        if row is None:
            return "alert"
        days_old = (on - row.date).days
        if days_old > 10:
            return "alert"
        if days_old > warn_threshold:
            worst = "warn"
    return worst
