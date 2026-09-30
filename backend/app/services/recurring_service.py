"""docs/03-domain-logic.md §6 "Recurring plans"."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import (
    Category,
    ContributionSource,
    PlanKind,
    TxnSource,
    TxnStatus,
    TxnType,
    ValuationMethod,
)
from app.core.errors import DomainError, NotFoundError
from app.engine import recurring
from app.models.accounts import Account, AccountOwner
from app.models.broker_links import BrokerLink
from app.models.instruments import Instrument
from app.models.recurring import RecurringPlan, RecurringPlanAllocation
from app.models.transactions import Transaction
from app.schemas.recurring import PlanAllocationIn, RecurringPlanCreate, RecurringPlanUpdate
from app.services import price_service

SHARE_TOLERANCE = 1e-6
MONEY_EPS = 0.005

# docs §6: "allocations only on holdings accounts; overpayment plans only on loans".
LOAN_CATEGORIES = {Category.mortgage, Category.loan, Category.other_liability}


def to_engine(plan: RecurringPlan) -> recurring.Plan:
    return recurring.Plan(
        amount=plan.amount_gbp,
        frequency=plan.frequency.value if hasattr(plan.frequency, "value") else plan.frequency,
        start=plan.start_date,
        end=plan.end_date,
        day_of_month=plan.day_of_month,
        annual_increase_rate=plan.annual_increase_rate,
        tax_relief_rate=plan.tax_relief_rate,
    )


def _validate_allocations(account: Account, allocations: list[PlanAllocationIn]) -> None:
    if not allocations:
        return
    if account.valuation_method != ValuationMethod.holdings:
        raise DomainError(
            "validation", "Allocations are only valid for holdings accounts", field="allocations"
        )
    total = sum(a.weight for a in allocations)
    if abs(total - 1.0) > SHARE_TOLERANCE:
        raise DomainError("validation", "Allocation weights must sum to 100%", field="allocations")


def _validate_kind(account: Account, kind: PlanKind) -> None:
    if kind == PlanKind.overpayment:
        if account.valuation_method != ValuationMethod.amortising:
            raise DomainError(
                "validation",
                "Overpayment plans are only valid for loan/mortgage accounts",
                field="kind",
            )
    elif account.valuation_method == ValuationMethod.amortising:
        raise DomainError(
            "validation",
            "Loan/mortgage accounts only accept overpayment plans",
            field="kind",
        )


def _validate_auto_record(db: Session, account: Account, auto_record: bool | None) -> None:
    """A broker-synced account gets its real payments from the sync; recording the plan as well
    would count every payment twice. The plan still drives projections."""
    if auto_record and db.get(BrokerLink, account.id) is not None:
        raise DomainError(
            "validation",
            "This account syncs from Trading 212, which adds each payment when it lands. "
            "Auto-add stays off; the payment still counts in projections.",
            field="auto_record",
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_plan(db: Session, account: Account, payload: RecurringPlanCreate) -> RecurringPlan:
    _validate_kind(account, payload.kind)
    _validate_allocations(account, payload.allocations)
    _validate_auto_record(db, account, payload.auto_record)

    plan = RecurringPlan(
        account_id=account.id,
        name=payload.name,
        kind=payload.kind,
        amount_gbp=round(payload.amount_gbp, 2),
        frequency=payload.frequency,
        day_of_month=payload.day_of_month,
        start_date=payload.start_date,
        end_date=payload.end_date,
        annual_increase_rate=payload.annual_increase_rate,
        contribution_source=payload.contribution_source,
        tax_relief_rate=payload.tax_relief_rate,
        auto_record=payload.auto_record,
        is_active=payload.is_active,
    )
    db.add(plan)
    db.flush()
    for a in payload.allocations:
        db.add(RecurringPlanAllocation(plan_id=plan.id, instrument_id=a.instrument_id, weight=a.weight))
    db.commit()
    db.refresh(plan)

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account.id, payload.start_date)
    projection_service.bump_data_version()
    return plan


def update_plan(db: Session, plan: RecurringPlan, payload: RecurringPlanUpdate) -> RecurringPlan:
    account = db.get(Account, plan.account_id)
    if account is None:
        raise NotFoundError(f"Account {plan.account_id} not found")

    _validate_auto_record(db, account, payload.auto_record)
    data = payload.model_dump(exclude_unset=True, exclude={"allocations"})
    for field, value in data.items():
        setattr(plan, field, value)

    if payload.allocations is not None:
        _validate_allocations(account, payload.allocations)
        plan.allocations.clear()
        db.flush()
        for a in payload.allocations:
            plan.allocations.append(
                RecurringPlanAllocation(instrument_id=a.instrument_id, weight=a.weight)
            )

    db.commit()
    db.refresh(plan)

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(plan.account_id, plan.start_date)
    projection_service.bump_data_version()
    return plan


def get_plan(db: Session, plan_id: int) -> RecurringPlan:
    plan = db.get(RecurringPlan, plan_id)
    if plan is None:
        raise NotFoundError(f"Recurring plan {plan_id} not found")
    return plan


def delete_plan(db: Session, plan: RecurringPlan) -> None:
    account_id = plan.account_id
    start_date = plan.start_date
    db.delete(plan)
    db.commit()

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account_id, start_date)
    projection_service.bump_data_version()


def list_plans(
    db: Session, account_id: int | None = None, person_id: int | None = None
) -> list[RecurringPlan]:
    query = select(RecurringPlan)
    if account_id is not None:
        query = query.where(RecurringPlan.account_id == account_id)
    else:
        # Unscoped listings (e.g. "upcoming" on the Overview) should not surface plans on
        # archived accounts; a specific account's own Plans tab still shows its history.
        query = query.join(Account, Account.id == RecurringPlan.account_id).where(
            Account.is_archived.is_(False)
        )
    if person_id is not None:
        query = query.join(
            AccountOwner, AccountOwner.account_id == RecurringPlan.account_id
        ).where(AccountOwner.person_id == person_id)
    return list(db.scalars(query.order_by(RecurringPlan.start_date)).unique().all())


def next_occurrence(plan: RecurringPlan, on: date) -> date | None:
    engine_plan = to_engine(plan)
    dates = recurring.occurrence_dates(engine_plan, on, on + timedelta(days=730))
    return dates[0] if dates else None


def _upcoming_loan_payments(
    db: Session, on: date, end: date, person_id: int | None
) -> list[dict]:
    """Scheduled payments on loan/mortgage accounts. These come from the loan terms, not a
    recurring plan, so they are read off the same amortisation schedule the Mortgage tab shows."""
    from app.services import loan_service

    query = select(Account).where(
        Account.is_archived.is_(False), Account.valuation_method == ValuationMethod.amortising
    )
    if person_id is not None:
        query = query.join(AccountOwner, AccountOwner.account_id == Account.id).where(
            AccountOwner.person_id == person_id
        )
    out: list[dict] = []
    for account in db.scalars(query).unique().all():
        if account.loan_details is None:
            continue
        try:
            rows = loan_service.schedule(db, account)["rows"]
        except DomainError:
            continue  # No anchor balance yet: nothing to schedule from.
        for row in rows:
            if row.date > end:
                break
            if row.date < on or row.payment <= MONEY_EPS:
                continue
            payment = round(row.payment, 2)
            out.append(
                {
                    "date": row.date,
                    "plan_id": None,
                    "account_id": account.id,
                    "name": f"{account.name} payment",
                    "kind": "loan_payment",
                    "amount_gbp": payment,
                    "gross_amount_gbp": payment,
                }
            )
    return out


def upcoming(db: Session, days: int = 60, person_id: int | None = None) -> list[dict]:
    """docs §6 "Upcoming": occurrences in the next N days across active plans and scheduled
    loan payments, sorted by date."""
    on = date_today()
    end = on + timedelta(days=days)
    plans = [p for p in list_plans(db, person_id=person_id) if p.is_active]
    out: list[dict] = _upcoming_loan_payments(db, on, end, person_id)
    for plan in plans:
        engine_plan = to_engine(plan)
        for d in recurring.occurrence_dates(engine_plan, on, end):
            out.append(
                {
                    "date": d,
                    "plan_id": plan.id,
                    "account_id": plan.account_id,
                    "name": plan.name,
                    "kind": plan.kind,
                    "amount_gbp": round(recurring.amount_on(engine_plan, d), 2),
                    "gross_amount_gbp": round(recurring.gross_amount_on(engine_plan, d), 2),
                }
            )
    out.sort(key=lambda r: r["date"])
    return out


# ---------------------------------------------------------------------------
# record_due — docs/03-domain-logic.md §6
# ---------------------------------------------------------------------------


def _record_holdings_due(db: Session, plan: RecurringPlan, account: Account, on: date) -> None:
    engine_plan = to_engine(plan)
    net = round(recurring.amount_on(engine_plan, on), 2)
    gross = recurring.gross_amount_on(engine_plan, on)
    relief = round(gross - net, 2)

    db.add(
        Transaction(
            account_id=account.id,
            date=on,
            type=TxnType.DEPOSIT,
            amount_gbp=net,
            contribution_source=plan.contribution_source,
            status=TxnStatus.pending,
            source=TxnSource.recurring,
            recurring_plan_id=plan.id,
        )
    )
    if relief > 1e-6:
        db.add(
            Transaction(
                account_id=account.id,
                date=on,
                type=TxnType.DEPOSIT,
                amount_gbp=relief,
                contribution_source=ContributionSource.tax_relief,
                status=TxnStatus.pending,
                source=TxnSource.recurring,
                recurring_plan_id=plan.id,
            )
        )

    for allocation in plan.allocations:
        instrument = db.get(Instrument, allocation.instrument_id)
        if instrument is None:
            continue
        amount = round(gross * allocation.weight, 2)
        price = price_service.price_gbp(db, instrument, on, live=False)
        if price.price_gbp <= 0:
            continue  # No price -> skip the BUY, leave the cash (docs §6).
        units = amount / price.price_gbp
        db.add(
            Transaction(
                account_id=account.id,
                instrument_id=instrument.id,
                date=on,
                type=TxnType.BUY,
                units=round(units, 8),
                price_native=price.price_gbp,
                amount_gbp=round(-amount, 2),
                status=TxnStatus.pending,
                source=TxnSource.recurring,
                recurring_plan_id=plan.id,
            )
        )


def record_due(db: Session, on: date | None = None) -> list[RecurringPlan]:
    """For every active, auto_record plan: write pending transactions for holdings accounts
    (balance/amortising accounts get nothing written — their valuation already rolls forward
    expected contributions). Idempotent: a second call with the same `on` is a no-op because
    `last_recorded_date` has already caught up to `on`."""
    on = on or date_today()
    plans = list(
        db.scalars(
            select(RecurringPlan).where(
                RecurringPlan.is_active.is_(True), RecurringPlan.auto_record.is_(True)
            )
        ).all()
    )
    touched: list[RecurringPlan] = []
    for plan in plans:
        account = db.get(Account, plan.account_id)
        if account is None or db.get(BrokerLink, account.id) is not None:
            continue
        engine_plan = to_engine(plan)
        from_date = (plan.last_recorded_date or (plan.start_date - timedelta(days=1))) + timedelta(
            days=1
        )
        if from_date > on:
            continue
        due_dates = recurring.occurrence_dates(engine_plan, from_date, on)
        if not due_dates:
            continue
        if account.valuation_method == ValuationMethod.holdings:
            for d in due_dates:
                _record_holdings_due(db, plan, account, d)
        plan.last_recorded_date = on
        touched.append(plan)

    db.commit()

    if touched:
        from app.services import snapshot_service

        for account_id in {p.account_id for p in touched}:
            snapshot_service.request_rebuild(account_id, on)

    return touched
