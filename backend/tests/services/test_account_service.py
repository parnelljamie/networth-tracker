from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Category, TxnType, ValuationMethod, Wrapper
from app.core.errors import DomainError
from app.models.accounts import Account, AccountOwner
from app.models.balances import BalanceEntry
from app.models.people import Person
from app.models.snapshots import AccountSnapshot
from app.models.transactions import Transaction
from app.schemas.account import AccountCreate, InitialBalanceIn, OwnerShareIn
from app.services import account_service


def _make_people(db: Session) -> tuple[Person, Person]:
    james = Person(name="James")
    sam = Person(name="Sam")
    db.add_all([james, sam])
    db.commit()
    db.refresh(james)
    db.refresh(sam)
    return james, sam


def test_validate_combination_rejects_wrapper_not_allowed_for_category():
    with pytest.raises(DomainError):
        account_service.validate_combination(Category.cash, Wrapper.sipp, ValuationMethod.balance)


def test_validate_combination_rejects_method_not_allowed_for_category():
    with pytest.raises(DomainError):
        account_service.validate_combination(Category.cash, Wrapper.none, ValuationMethod.model)


def test_validate_owners_rejects_two_owners_for_wrapped_account():
    owners = [OwnerShareIn(person_id=1, share=0.5), OwnerShareIn(person_id=2, share=0.5)]
    with pytest.raises(DomainError):
        account_service.validate_owners(Wrapper.isa, owners)


def test_validate_owners_requires_shares_sum_to_one():
    owners = [OwnerShareIn(person_id=1, share=0.5), OwnerShareIn(person_id=2, share=0.4)]
    with pytest.raises(DomainError):
        account_service.validate_owners(Wrapper.none, owners)


def test_validate_owners_accepts_joint_50_50():
    owners = [OwnerShareIn(person_id=1, share=0.5), OwnerShareIn(person_id=2, share=0.5)]
    account_service.validate_owners(Wrapper.none, owners)  # does not raise


def test_create_account_persists_owners_and_initial_balance(db: Session):
    james, sam = _make_people(db)
    payload = AccountCreate(
        name="Joint Current Account",
        category=Category.cash,
        wrapper=Wrapper.none,
        valuation_method=ValuationMethod.balance,
        owners=[OwnerShareIn(person_id=james.id, share=0.5), OwnerShareIn(person_id=sam.id, share=0.5)],
        initial_balance=InitialBalanceIn(date="2026-09-15", balance_gbp=2000.0),
    )
    account = account_service.create_account(db, payload)

    assert len(account.owners) == 2
    assert account.balance_entries[0].balance_gbp == 2000.0
    assert account.is_liquid is True  # cash default


def test_db_pension_defaults_to_excluded_from_networth(db: Session):
    james, _ = _make_people(db)
    payload = AccountCreate(
        name="Final salary pension",
        category=Category.pension,
        wrapper=Wrapper.db_pension,
        valuation_method=ValuationMethod.balance,
        owners=[OwnerShareIn(person_id=james.id, share=1.0)],
    )
    account = account_service.create_account(db, payload)
    assert account.include_in_networth is False


def test_delete_account_with_history_succeeds_and_cascades(db: Session):
    james, _ = _make_people(db)
    payload = AccountCreate(
        name="Cash",
        category=Category.cash,
        wrapper=Wrapper.none,
        valuation_method=ValuationMethod.balance,
        owners=[OwnerShareIn(person_id=james.id, share=1.0)],
        initial_balance=InitialBalanceIn(date="2026-09-15", balance_gbp=100.0),
    )
    account = account_service.create_account(db, payload)
    account_id = account.id
    db.add(
        Transaction(
            account_id=account_id,
            date=date(2026, 9, 15),
            type=TxnType.DEPOSIT,
            amount_gbp=100.0,
        )
    )
    db.add(AccountSnapshot(account_id=account_id, date=date(2026, 9, 15), value_gbp=100.0))
    db.commit()

    account_service.delete_account(db, account)

    assert db.get(Account, account_id) is None
    for model in (BalanceEntry, Transaction, AccountSnapshot, AccountOwner):
        remaining = db.scalars(select(model).where(model.account_id == account_id)).all()
        assert remaining == [], f"{model.__name__} rows left behind"


def test_archived_accounts_excluded_by_default(db: Session):
    james, _ = _make_people(db)
    payload = AccountCreate(
        name="Old account",
        category=Category.cash,
        wrapper=Wrapper.none,
        valuation_method=ValuationMethod.balance,
        owners=[OwnerShareIn(person_id=james.id, share=1.0)],
    )
    account = account_service.create_account(db, payload)
    account_service.set_archived(db, account, True)

    assert account_service.list_accounts(db) == []
    assert len(account_service.list_accounts(db, include_archived=True)) == 1
