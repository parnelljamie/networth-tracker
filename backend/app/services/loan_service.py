"""docs/03-domain-logic.md §5 "Mortgages and loans"."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import BalanceSource, Category, OverpaymentEffect, RateType
from app.core.errors import DomainError, NotFoundError
from app.engine import amortisation
from app.engine.dates import add_months, clamp_day
from app.models.accounts import Account
from app.models.balances import BalanceEntry
from app.models.loans import LoanOverpayment, LoanRatePeriod
from app.schemas.loan import OverpaymentIn, RatePeriodIn

MONEY_EPS = amortisation.MONEY_EPS

ANCHOR_SOURCES = (BalanceSource.statement, BalanceSource.manual)


@dataclass(frozen=True)
class Anchor:
    date: date
    balance_gbp: float
    source: BalanceSource


# ---------------------------------------------------------------------------
# Terms, anchor, overpayments
# ---------------------------------------------------------------------------


def terms_for(account: Account) -> amortisation.LoanTerms:
    ld = account.loan_details
    if ld is None:
        raise DomainError("validation", "Account has no loan details", field="loan")
    periods = tuple(
        amortisation.RatePeriod(
            start=rp.start_date,
            annual_rate=rp.annual_rate,
            end=rp.end_date,
            payment_override=rp.payment_override_gbp,
        )
        for rp in sorted(ld.rate_periods, key=lambda r: r.start_date)
    )
    return amortisation.LoanTerms(
        maturity=ld.maturity_date,
        fallback_rate=ld.fallback_rate,
        rate_periods=periods,
        payment_day=ld.payment_day,
        repayment_type=ld.repayment_type.value,
        overpayment_effect=ld.overpayment_effect.value,
    )


def validate_no_overlap(
    existing: list[LoanRatePeriod],
    new_start: date,
    new_end: date | None,
    exclude_id: int | None = None,
) -> None:
    """docs/02-data-model.md: "Periods for one account must not overlap (validate on write)"."""
    n_end = new_end or date.max
    for rp in existing:
        if exclude_id is not None and rp.id == exclude_id:
            continue
        rp_end = rp.end_date or date.max
        if new_start <= rp_end and rp.start_date <= n_end:
            raise DomainError(
                "validation", "Rate periods for a loan must not overlap", field="rate_periods"
            )


def get_anchor(db: Session, account: Account) -> Anchor:
    entry = db.scalars(
        select(BalanceEntry)
        .where(BalanceEntry.account_id == account.id, BalanceEntry.source.in_(ANCHOR_SOURCES))
        .order_by(BalanceEntry.date.desc())
        .limit(1)
    ).first()
    if entry is not None:
        return Anchor(date=entry.date, balance_gbp=entry.balance_gbp, source=entry.source)

    ld = account.loan_details
    if ld is not None and ld.original_amount_gbp is not None and ld.start_date is not None:
        return Anchor(date=ld.start_date, balance_gbp=ld.original_amount_gbp, source=BalanceSource.estimate)

    raise DomainError(
        "validation",
        "Loan has no statement balance and no original amount/start date to anchor from",
        field="loan",
    )


def actual_overpayments(db: Session, account_id: int) -> list[tuple[date, float]]:
    rows = db.scalars(
        select(LoanOverpayment).where(
            LoanOverpayment.account_id == account_id, LoanOverpayment.is_planned.is_(False)
        )
    ).all()
    return [(r.date, r.amount_gbp) for r in rows]


def _planned_overpayment_rows(db: Session, account_id: int) -> list[LoanOverpayment]:
    return list(
        db.scalars(
            select(LoanOverpayment).where(
                LoanOverpayment.account_id == account_id, LoanOverpayment.is_planned.is_(True)
            )
        ).all()
    )


def _planned_overpayments(db: Session, account_id: int) -> list[tuple[date, float]]:
    """is_planned rows kept for projections. Recurring `overpayment` plans (docs §5) arrive with
    recurring_plans in Phase 5; until then planned overpayments are explicit dated rows only."""
    return [(r.date, r.amount_gbp) for r in _planned_overpayment_rows(db, account_id)]


def estimated_balance_today(db: Session, account: Account, on: date | None = None) -> tuple[float, Anchor]:
    on = on or date_today()
    anchor = get_anchor(db, account)
    terms = terms_for(account)
    actual = actual_overpayments(db, account.id)
    rows = amortisation.build_schedule(terms, anchor.balance_gbp, anchor.date, actual, until=on)
    balance = amortisation.balance_on(rows, on, anchor.balance_gbp)
    return balance, anchor


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def _rate_period_row_on(account: Account, on: date) -> LoanRatePeriod | None:
    ld = account.loan_details
    covering = [
        rp for rp in ld.rate_periods if rp.start_date <= on and (rp.end_date is None or on <= rp.end_date)
    ]
    return max(covering, key=lambda r: r.start_date) if covering else None


def _allowance_warnings(
    db: Session, account: Account, terms: amortisation.LoanTerms, rows: list[amortisation.ScheduleRow]
) -> list[dict]:
    """docs §5 "Allowance warnings": 12-month windows from each fixed period's start; allowed =
    overpayment_allowance_rate x opening balance of the first row in the window."""
    ld = account.loan_details
    combined: dict[date, float] = {}
    for d, amount in actual_overpayments(db, account.id) + _planned_overpayments(db, account.id):
        combined[d] = combined.get(d, 0.0) + amount

    warnings: list[dict] = []
    for period in ld.rate_periods:
        if period.rate_type != RateType.fixed:
            continue
        window_start = period.start_date
        period_end = period.end_date or ld.maturity_date
        while window_start < period_end:
            window_end = add_months(window_start, 12)
            opening_row = next((r for r in rows if r.date >= window_start), None)
            if opening_row is None:
                break
            allowed = ld.overpayment_allowance_rate * opening_row.opening_balance
            planned_amount = sum(
                amount for d, amount in combined.items() if window_start <= d < window_end
            )
            if planned_amount > allowed + MONEY_EPS:
                warnings.append(
                    {
                        "period_label": period.label,
                        "year_start": window_start,
                        "allowed_gbp": round(allowed, 2),
                        "planned_gbp": round(planned_amount, 2),
                    }
                )
            window_start = window_end
    return warnings


def schedule(db: Session, account: Account, include_planned: bool = True) -> dict:
    on = date_today()
    balance, anchor = estimated_balance_today(db, account, on)
    terms = terms_for(account)
    planned = _planned_overpayments(db, account.id) if include_planned else []

    rows = amortisation.build_schedule(terms, balance, on, planned)
    baseline_rows = amortisation.build_schedule(terms, balance, on, [])
    summary = amortisation.summarise(rows)
    baseline_summary = amortisation.summarise(baseline_rows)

    period_row = _rate_period_row_on(account, on)
    current_rate = period_row.annual_rate if period_row is not None else terms.fallback_rate

    current_period_out = None
    if period_row is not None and period_row.end_date is not None:
        current_period_out = {
            "label": period_row.label,
            "end_date": period_row.end_date,
            "days_left": (period_row.end_date - on).days,
        }

    monthly_payment = rows[0].payment if rows else 0.0

    summary_out = {
        "anchor": {"date": anchor.date, "balance_gbp": anchor.balance_gbp, "source": anchor.source},
        "estimated_balance_today_gbp": round(balance, 2),
        "current_rate": current_rate,
        "current_period": current_period_out,
        "monthly_payment_gbp": monthly_payment,
        "payoff_date": summary.payoff_date,
        "months_remaining": summary.n_payments,
        "total_interest_remaining_gbp": summary.total_interest,
        "baseline": {
            "payoff_date": baseline_summary.payoff_date,
            "total_interest_remaining_gbp": baseline_summary.total_interest,
        },
    }
    return {
        "summary": summary_out,
        "rows": rows,
        "allowance_warnings": _allowance_warnings(db, account, terms, rows),
    }


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------


def _monthly_overpayment_dates(terms: amortisation.LoanTerms, on: date) -> list[date]:
    """Every payment date from the next payment after `on` to maturity."""
    dates: list[date] = []
    d = amortisation.first_payment_after(on, terms.payment_day)
    while d <= terms.maturity:
        dates.append(d)
        nxt = add_months(date(d.year, d.month, 1), 1)
        d = clamp_day(nxt.year, nxt.month, terms.payment_day)
    return dates


def simulated_overpayments(
    db: Session,
    account: Account,
    extra_monthly_gbp: float,
    lump_sums: list[tuple[date, float]],
    on: date | None = None,
) -> list[tuple[date, float]]:
    """The full list of (date, amount) overpayments a simulation applies: existing planned rows
    plus `extra_monthly_gbp` as a monthly plan from next month, plus one-off lump sums."""
    on = on or date_today()
    terms = terms_for(account)
    overpayments = list(_planned_overpayments(db, account.id))
    if extra_monthly_gbp > 0:
        overpayments += [(d, extra_monthly_gbp) for d in _monthly_overpayment_dates(terms, on)]
    overpayments += list(lump_sums)
    return overpayments


def simulate(
    db: Session,
    account: Account,
    extra_monthly_gbp: float,
    lump_sums: list[tuple[date, float]],
    overpayment_effect: OverpaymentEffect | None = None,
) -> dict:
    on = date_today()
    balance, _anchor = estimated_balance_today(db, account, on)
    terms = terms_for(account)
    if overpayment_effect is not None:
        terms = replace(terms, overpayment_effect=overpayment_effect.value)

    baseline_overpayments = _planned_overpayments(db, account.id)
    baseline_rows = amortisation.build_schedule(terms, balance, on, baseline_overpayments)
    baseline_summary = amortisation.summarise(baseline_rows)

    sim_overpayments = simulated_overpayments(db, account, extra_monthly_gbp, lump_sums, on)
    sim_rows = amortisation.build_schedule(terms, balance, on, sim_overpayments)
    sim_summary = amortisation.summarise(sim_rows)

    first_changed_payment_gbp = None
    for b, s in zip(baseline_rows, sim_rows, strict=False):
        if abs(b.payment - s.payment) > MONEY_EPS:
            first_changed_payment_gbp = s.payment
            break
    if first_changed_payment_gbp is None and len(sim_rows) != len(baseline_rows):
        first_changed_payment_gbp = sim_rows[-1].payment if sim_rows else 0.0

    timeline = sorted({r.date for r in baseline_rows} | {r.date for r in sim_rows})
    chart = [
        {
            "date": d,
            "baseline_balance_gbp": amortisation.balance_on(baseline_rows, d, balance),
            "simulated_balance_gbp": amortisation.balance_on(sim_rows, d, balance),
        }
        for d in timeline
    ]

    return {
        "payoff_date": sim_summary.payoff_date,
        "months_saved": baseline_summary.n_payments - sim_summary.n_payments,
        "interest_saved_gbp": round(baseline_summary.total_interest - sim_summary.total_interest, 2),
        "first_changed_payment_gbp": first_changed_payment_gbp,
        "chart": chart,
    }


def save_simulation_as_plan(
    db: Session,
    account: Account,
    extra_monthly_gbp: float,
    lump_sums: list[tuple[date, float]],
) -> list[LoanOverpayment]:
    """"Save as plan" (docs/05-ui.md): persist the simulated overpayments as planned rows."""
    on = date_today()
    overpayments = []
    if extra_monthly_gbp > 0:
        terms = terms_for(account)
        for d in _monthly_overpayment_dates(terms, on):
            overpayments.append((d, extra_monthly_gbp, "Overpayment plan"))
    for d, amount in lump_sums:
        overpayments.append((d, amount, "Lump sum (simulator)"))

    created: list[LoanOverpayment] = []
    for d, amount, note in overpayments:
        row = LoanOverpayment(
            account_id=account.id, date=d, amount_gbp=round(amount, 2), is_planned=True, notes=note
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)

    if created:
        from app.services import projection_service, snapshot_service

        earliest = min(r.date for r in created)
        snapshot_service.request_rebuild(account.id, earliest)
        projection_service.bump_data_version()
    return created


# ---------------------------------------------------------------------------
# Rate periods CRUD
# ---------------------------------------------------------------------------


def list_rate_periods(db: Session, account_id: int) -> list[LoanRatePeriod]:
    return list(
        db.scalars(
            select(LoanRatePeriod)
            .where(LoanRatePeriod.account_id == account_id)
            .order_by(LoanRatePeriod.start_date)
        ).all()
    )


def create_rate_period(db: Session, account: Account, payload: RatePeriodIn) -> LoanRatePeriod:
    existing = list_rate_periods(db, account.id)
    validate_no_overlap(existing, payload.start_date, payload.end_date)
    row = LoanRatePeriod(account_id=account.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    _rebuild_from_loan_change(db, account.id)
    return row


def get_rate_period(db: Session, rate_period_id: int) -> LoanRatePeriod:
    row = db.get(LoanRatePeriod, rate_period_id)
    if row is None:
        raise NotFoundError(f"Rate period {rate_period_id} not found")
    return row


def update_rate_period(db: Session, row: LoanRatePeriod, payload: RatePeriodIn) -> LoanRatePeriod:
    existing = [rp for rp in list_rate_periods(db, row.account_id) if rp.id != row.id]
    validate_no_overlap(existing, payload.start_date, payload.end_date)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    _rebuild_from_loan_change(db, row.account_id)
    return row


def delete_rate_period(db: Session, row: LoanRatePeriod) -> None:
    account_id = row.account_id
    db.delete(row)
    db.commit()
    _rebuild_from_loan_change(db, account_id)


# ---------------------------------------------------------------------------
# Overpayments CRUD
# ---------------------------------------------------------------------------


def list_overpayments(db: Session, account_id: int) -> list[LoanOverpayment]:
    return list(
        db.scalars(
            select(LoanOverpayment)
            .where(LoanOverpayment.account_id == account_id)
            .order_by(LoanOverpayment.date.desc())
        ).all()
    )


def create_overpayment(db: Session, account: Account, payload: OverpaymentIn) -> LoanOverpayment:
    row = LoanOverpayment(account_id=account.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    _rebuild_from_loan_change(db, account.id, from_date=payload.date)
    return row


def get_overpayment(db: Session, overpayment_id: int) -> LoanOverpayment:
    row = db.get(LoanOverpayment, overpayment_id)
    if row is None:
        raise NotFoundError(f"Overpayment {overpayment_id} not found")
    return row


def update_overpayment(db: Session, row: LoanOverpayment, payload: OverpaymentIn) -> LoanOverpayment:
    account_id = row.account_id
    earliest = min(row.date, payload.date)
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    _rebuild_from_loan_change(db, account_id, from_date=earliest)
    return row


def delete_overpayment(db: Session, row: LoanOverpayment) -> None:
    account_id = row.account_id
    from_date = row.date
    db.delete(row)
    db.commit()
    _rebuild_from_loan_change(db, account_id, from_date=from_date)


def _rebuild_from_loan_change(db: Session, account_id: int, from_date: date | None = None) -> None:
    """Any rate-period or overpayment change can move the whole schedule — rebuild snapshots
    from the earlier of the change date and the loan's statement anchor."""
    from app.services import projection_service, snapshot_service

    account = db.get(Account, account_id)
    if account is None:
        return
    entry = db.scalars(
        select(BalanceEntry)
        .where(BalanceEntry.account_id == account_id)
        .order_by(BalanceEntry.date)
        .limit(1)
    ).first()
    candidates = [d for d in (from_date, entry.date if entry else None) if d is not None]
    snapshot_service.request_rebuild(account_id, min(candidates) if candidates else date_today())
    projection_service.bump_data_version()


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------


def equity(db: Session, property_account: Account) -> dict:
    from app.services import valuation_service

    if property_account.category != Category.property:
        raise DomainError("validation", "Equity only applies to property accounts", field="category")

    on = date_today()
    value_valuation = valuation_service.value_account(db, property_account, on, live=True)
    value_gbp = value_valuation.value_gbp  # unsigned (asset)

    secured_loans = list(
        db.scalars(
            select(Account).where(
                Account.is_archived.is_(False),
            )
        ).all()
    )
    secured_loans = [
        a
        for a in secured_loans
        if a.loan_details is not None and a.loan_details.secured_on_account_id == property_account.id
    ]

    loans_out = []
    total_owed = 0.0
    for loan_account in secured_loans:
        balance, _anchor = estimated_balance_today(db, loan_account, on)
        loans_out.append({"account_id": loan_account.id, "name": loan_account.name, "owed_gbp": round(balance, 2)})
        total_owed += balance

    equity_gbp = round(value_gbp - total_owed, 2)
    ltv = round(total_owed / value_gbp, 4) if value_gbp > 0 else None

    by_person = [
        {"person_id": o.person_id, "equity_gbp": round(equity_gbp * o.share, 2)}
        for o in property_account.owners
    ]

    return {
        "value_gbp": value_gbp,
        "loans": loans_out,
        "equity_gbp": equity_gbp,
        "ltv": ltv,
        "by_person": by_person,
    }
