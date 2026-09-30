from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now_utc, today
from app.core.enums import Category, TxnStatus, ValuationMethod
from app.engine.dates import add_months
from app.models.people import Person
from app.models.positions import Position
from app.models.transactions import Transaction
from app.schemas.networth import (
    CategoryShare,
    ChangeFigure,
    Freshness,
    NetWorthChanges,
    NetWorthCurrent,
    PersonShare,
    StaleAccount,
)
from app.services import account_service, price_service, snapshot_service, valuation_service

TOP_MOVERS_LIMIT = 5


def _change_reference_dates(on: date) -> dict[str, date]:
    """docs/04-api.md NetWorthCurrent.changes: yesterday, 7 days ago, one month ago,
    31 Dec last year, one year ago."""
    return {
        "day": on - timedelta(days=1),
        "week": on - timedelta(days=7),
        "month": add_months(on, -1),
        "ytd": date(on.year - 1, 12, 31),
        "year": add_months(on, -12),
    }


def _compute_changes(db: Session, scope_ids: set[int], on: date, total: float) -> NetWorthChanges:
    figures: dict[str, ChangeFigure] = {}
    for key, ref_date in _change_reference_dates(on).items():
        ref_total = snapshot_service.total_on_or_before(db, scope_ids, ref_date)
        if ref_total is None:
            figures[key] = ChangeFigure(abs_gbp=None, pct=None)
        else:
            abs_gbp = round(total - ref_total, 2)
            pct = round(abs_gbp / abs(ref_total), 4) if ref_total else None
            figures[key] = ChangeFigure(abs_gbp=abs_gbp, pct=pct)
    return NetWorthChanges(**figures)


def get_current(db: Session, person_id: int | None = None) -> NetWorthCurrent:
    on = today()
    accounts = account_service.list_accounts(db, include_archived=False)
    people = list(db.scalars(select(Person).where(Person.is_archived.is_(False))).all())
    household_ids = {p.id for p in people if p.include_in_household}
    scope_ids = {person_id} if person_id is not None else household_ids

    summaries = []
    total = assets = liabilities = liquid = illiquid = 0.0
    by_category_totals: dict[Category, float] = {}
    by_person_totals: dict[int, float] = {p.id: 0.0 for p in people}
    stale_accounts: list[StaleAccount] = []

    by_asset_class_totals: dict[str, float] = {}
    movers: list[dict] = []
    prices_updated_at = None

    for account in accounts:
        summary = account_service.build_account_summary(db, account, on, scope_ids)
        summaries.append(summary)

        if summary.staleness in ("warn", "alert"):
            days_since = valuation_service.days_since_last_entry(db, account, on)
            if days_since is not None:
                stale_accounts.append(
                    StaleAccount(
                        account_id=account.id,
                        name=account.name,
                        days_since=days_since,
                        staleness=summary.staleness,
                    )
                )

        if not account.include_in_networth:
            continue

        value = summary.scoped_value_gbp
        total += value
        if value >= 0:
            assets += value
        else:
            liabilities += value
        if account.is_liquid:
            liquid += value
        else:
            illiquid += value
        by_category_totals[account.category] = by_category_totals.get(account.category, 0.0) + value

        for owner in account.owners:
            if owner.person_id in by_person_totals:
                by_person_totals[owner.person_id] += valuation_service.scoped_value(
                    summary.value_gbp, account, {owner.person_id}
                )

        if account.valuation_method == ValuationMethod.holdings:
            account_share = sum(o.share for o in account.owners if o.person_id in scope_ids)
            if account_share <= 0:
                continue
            positions = list(db.scalars(select(Position).where(Position.account_id == account.id)).all())
            for pos in positions:
                if pos.instrument.last_price_at is not None:
                    prices_updated_at = (
                        pos.instrument.last_price_at
                        if prices_updated_at is None
                        else max(prices_updated_at, pos.instrument.last_price_at)
                    )
                result = price_service.price_gbp(db, pos.instrument, on, live=True)
                scoped_value = pos.units * result.price_gbp * account_share
                by_asset_class_totals[pos.instrument.asset_class.value] = (
                    by_asset_class_totals.get(pos.instrument.asset_class.value, 0.0) + scoped_value
                )

                day_change = price_service.day_change_contribution(pos.instrument, pos.units, on, db) * account_share
                if day_change != 0:
                    prev_value = scoped_value - day_change
                    movers.append(
                        {
                            "instrument_id": pos.instrument.id,
                            "symbol": pos.instrument.symbol,
                            "name": pos.instrument.name,
                            "day_change_gbp": round(day_change, 2),
                            "day_change_pct": round(day_change / prev_value, 4) if prev_value else None,
                        }
                    )

    by_category = [
        CategoryShare(
            category=category.value,
            value_gbp=round(value, 2),
            share_of_assets=round(value / assets, 4) if assets else 0.0,
        )
        for category, value in sorted(by_category_totals.items(), key=lambda kv: kv[0].value)
    ]
    by_person = [
        PersonShare(person_id=p.id, name=p.name, color=p.color, value_gbp=round(by_person_totals[p.id], 2))
        for p in people
    ]
    by_asset_class = [
        {"asset_class": ac, "value_gbp": round(v, 2)}
        for ac, v in sorted(by_asset_class_totals.items(), key=lambda kv: kv[0])
    ]
    top_movers = sorted(movers, key=lambda m: abs(m["day_change_gbp"]), reverse=True)[:TOP_MOVERS_LIMIT]

    pending_transactions = (
        db.scalar(select(func.count()).select_from(Transaction).where(Transaction.status == TxnStatus.pending))
        or 0
    )

    return NetWorthCurrent(
        as_of=now_utc(),
        person_id=person_id,
        total_gbp=round(total, 2),
        assets_gbp=round(assets, 2),
        liabilities_gbp=round(liabilities, 2),
        liquid_gbp=round(liquid, 2),
        illiquid_gbp=round(illiquid, 2),
        changes=_compute_changes(db, scope_ids, on, total),
        by_category=by_category,
        by_person=by_person,
        by_asset_class=by_asset_class,
        accounts=summaries,
        top_movers=top_movers,
        freshness=Freshness(prices_updated_at=prices_updated_at, stale_accounts=stale_accounts),
        pending_transactions=pending_transactions,
    )
