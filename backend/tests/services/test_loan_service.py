from __future__ import annotations

from datetime import date

from freezegun import freeze_time
from sqlalchemy.orm import Session

from app.core.enums import BalanceSource, Category, RateType, ValuationMethod, Wrapper
from app.engine import amortisation
from app.models.people import Person
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.schemas.balance import BalanceEntryIn
from app.schemas.loan import LoanDetailsCreate, LoanDetailsIn, OverpaymentIn, RatePeriodIn
from app.services import account_service, balance_service, loan_service


def _person(db: Session, name: str = "James") -> Person:
    person = Person(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _mortgage(
    db: Session,
    owner_id: int,
    *,
    original_amount: float = 200000.0,
    start: date = date(2026, 9, 1),
    maturity: date = date(2051, 9, 1),
    fallback_rate: float = 0.045,
    rate_periods: list[RatePeriodIn] | None = None,
    name: str = "Mortgage",
):
    if rate_periods is None:
        rate_periods = [
            RatePeriodIn(start_date=start, end_date=None, annual_rate=fallback_rate, rate_type=RateType.fixed)
        ]
    return account_service.create_account(
        db,
        AccountCreate(
            name=name,
            category=Category.mortgage,
            wrapper=Wrapper.none,
            valuation_method=ValuationMethod.amortising,
            owners=[OwnerShareIn(person_id=owner_id, share=1.0)],
            loan=LoanDetailsCreate(
                original_amount_gbp=original_amount,
                start_date=start,
                maturity_date=maturity,
                fallback_rate=fallback_rate,
                rate_periods=rate_periods,
            ),
        ),
    )


def test_schedule_matches_the_engine_directly(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(db, james.id)
        db.refresh(account)
        result = loan_service.schedule(db, account)

        terms = loan_service.terms_for(account)
        expected_rows = amortisation.build_schedule(terms, 200000.0, date(2026, 9, 1), [])

    assert [r.payment for r in result["rows"]] == [r.payment for r in expected_rows]
    assert [r.closing_balance for r in result["rows"]] == [r.closing_balance for r in expected_rows]
    assert result["summary"]["monthly_payment_gbp"] == 1111.66


def test_200k_at_4_5pct_over_25y_pays_1111_66_a_month(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(
            db, james.id, original_amount=200000.0, start=date(2026, 9, 1), maturity=date(2051, 9, 1),
            fallback_rate=0.045,
        )
        db.refresh(account)
        result = loan_service.schedule(db, account)
    assert result["summary"]["monthly_payment_gbp"] == 1111.66


def test_payment_changes_on_first_payment_after_a_fix_ends(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(
            db,
            james.id,
            fallback_rate=0.06,
            rate_periods=[
                RatePeriodIn(
                    start_date=date(2026, 9, 1),
                    end_date=date(2028, 8, 31),
                    annual_rate=0.045,
                    rate_type=RateType.fixed,
                    label="2yr fix",
                )
            ],
        )
        db.refresh(account)
        result = loan_service.schedule(db, account)

    rows = result["rows"]
    last_in_fix = [r for r in rows if r.date < date(2028, 9, 1)][-1]
    first_after_fix = [r for r in rows if r.date >= date(2028, 9, 1)][0]
    assert last_in_fix.payment != first_after_fix.payment
    assert first_after_fix.annual_rate == 0.06


def test_statement_balance_re_anchors_the_estimate_and_schedule(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(db, james.id)
        db.refresh(account)
        before_balance, before_anchor = loan_service.estimated_balance_today(db, account)
        assert before_anchor.balance_gbp == 200000.0

        balance_service.upsert_balance(
            db, account, BalanceEntryIn(date=date(2026, 10, 1), balance_gbp=195000.0, source=BalanceSource.statement)
        )
        db.refresh(account)

        after_balance, after_anchor = loan_service.estimated_balance_today(db, account)
        assert after_anchor.balance_gbp == 195000.0
        assert after_anchor.date == date(2026, 10, 1)
        assert after_balance != before_balance


def test_actual_overpayments_reduce_the_estimated_balance_but_planned_do_not(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(db, james.id)
        db.refresh(account)

        loan_service.create_overpayment(
            db, account, OverpaymentIn(date=date(2026, 10, 1), amount_gbp=5000.0, is_planned=False)
        )
        db.refresh(account)
        actual_balance, _ = loan_service.estimated_balance_today(db, account, date(2026, 11, 1))

        account2 = _mortgage(db, james.id, name="Mortgage 2")
        db.refresh(account2)
        loan_service.create_overpayment(
            db, account2, OverpaymentIn(date=date(2026, 10, 1), amount_gbp=5000.0, is_planned=True)
        )
        db.refresh(account2)
        planned_balance, _ = loan_service.estimated_balance_today(db, account2, date(2026, 11, 1))

    assert actual_balance < planned_balance


def test_simulate_extra_monthly_shortens_the_term_and_saves_interest(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(db, james.id)
        db.refresh(account)
        sim = loan_service.simulate(db, account, extra_monthly_gbp=200.0, lump_sums=[])

    assert sim["months_saved"] > 0
    assert sim["interest_saved_gbp"] > 0
    assert sim["payoff_date"] is not None


def test_save_simulation_as_plan_persists_planned_overpayments(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(db, james.id)
        db.refresh(account)
        created = loan_service.save_simulation_as_plan(db, account, extra_monthly_gbp=200.0, lump_sums=[])

    assert len(created) > 0
    assert all(row.is_planned for row in created)
    stored = loan_service.list_overpayments(db, account.id)
    assert len(stored) == len(created)


def test_equity_splits_by_owner_share(db: Session):
    james = _person(db, "James")
    sam = _person(db, "Sam")
    with freeze_time("2026-09-16"):
        prop = account_service.create_account(
            db,
            AccountCreate(
                name="Home",
                category=Category.property,
                wrapper=Wrapper.none,
                valuation_method=ValuationMethod.model,
                owners=[OwnerShareIn(person_id=james.id, share=0.5), OwnerShareIn(person_id=sam.id, share=0.5)],
                initial_balance=InitialBalanceIn(date=date(2026, 9, 1), balance_gbp=400000.0),
                growth_model={"annual_rate": 0.0, "method": "compound"},
                property={"address": "1 Test St", "purchase_date": "2026-09-01", "purchase_price_gbp": 400000},
            ),
        )
        mortgage = _mortgage(db, james.id, original_amount=200000.0)
        db.refresh(mortgage)
        account_service.upsert_loan_details(
            db,
            mortgage,
            LoanDetailsIn(
                secured_on_account_id=prop.id,
                original_amount_gbp=200000.0,
                start_date=date(2026, 9, 1),
                maturity_date=date(2051, 9, 1),
                fallback_rate=0.045,
            ),
        )
        db.refresh(prop)

        eq = loan_service.equity(db, prop)

    assert eq["value_gbp"] == 400000.0
    assert eq["loans"] == [{"account_id": mortgage.id, "name": "Mortgage", "owed_gbp": 200000.0}]
    assert eq["equity_gbp"] == 200000.0
    assert eq["ltv"] == 0.5
    by_person = {row["person_id"]: row["equity_gbp"] for row in eq["by_person"]}
    assert by_person[james.id] == 100000.0
    assert by_person[sam.id] == 100000.0


def test_rate_period_overlap_is_rejected(db: Session):
    james = _person(db)
    with freeze_time("2026-09-16"):
        account = _mortgage(
            db,
            james.id,
            rate_periods=[
                RatePeriodIn(
                    start_date=date(2026, 9, 1), end_date=date(2028, 8, 31), annual_rate=0.045, rate_type=RateType.fixed
                )
            ],
        )
        db.refresh(account)
        import pytest

        from app.core.errors import DomainError

        with pytest.raises(DomainError):
            loan_service.create_rate_period(
                db,
                account,
                RatePeriodIn(
                    start_date=date(2027, 1, 1), end_date=date(2029, 1, 1), annual_rate=0.05, rate_type=RateType.fixed
                ),
            )
