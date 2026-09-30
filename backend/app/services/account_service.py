from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today as date_today
from app.core.enums import BalanceSource, Category, ValuationMethod, Wrapper
from app.core.errors import DomainError, NotFoundError
from app.models.accounts import Account, AccountOwner
from app.models.balances import BalanceEntry
from app.models.broker_links import BrokerLink
from app.models.growth import GrowthModel
from app.models.loans import LoanDetails, LoanRatePeriod
from app.models.people import Person
from app.models.positions import Position
from app.models.property import PropertyDetails
from app.schemas.account import (
    AccountCreate,
    AccountDetail,
    AccountSummary,
    AccountUpdate,
    GrowthModelIn,
    GrowthModelOut,
    OwnerShareIn,
    OwnerShareOut,
    PropertyDetailsIn,
    PropertyDetailsOut,
)
from app.schemas.db_pension import DbPensionDetailsIn, DbPensionDetailsOut
from app.schemas.loan import LoanDetailsIn, LoanDetailsOut
from app.services import db_pension_service, loan_service, valuation_service

# docs/02-data-model.md "Allowed combinations"
ALLOWED_WRAPPERS: dict[Category, set[Wrapper]] = {
    Category.investment: {Wrapper.isa, Wrapper.lisa, Wrapper.jisa, Wrapper.gia},
    Category.pension: {Wrapper.sipp, Wrapper.workplace_pension, Wrapper.db_pension},
    Category.cash: {Wrapper.none, Wrapper.isa, Wrapper.lisa, Wrapper.jisa},
    Category.property: {Wrapper.none},
    Category.mortgage: {Wrapper.none},
    Category.loan: {Wrapper.none},
    Category.credit_card: {Wrapper.none},
    Category.other_asset: {Wrapper.none},
    Category.other_liability: {Wrapper.none},
}

ALLOWED_METHODS: dict[Category, list[ValuationMethod]] = {
    Category.investment: [ValuationMethod.holdings, ValuationMethod.balance],
    Category.pension: [ValuationMethod.holdings, ValuationMethod.balance, ValuationMethod.defined_benefit],
    Category.cash: [ValuationMethod.balance],
    Category.property: [ValuationMethod.model],
    Category.mortgage: [ValuationMethod.amortising, ValuationMethod.balance],
    Category.loan: [ValuationMethod.amortising, ValuationMethod.balance],
    Category.credit_card: [ValuationMethod.balance],
    Category.other_asset: [ValuationMethod.model, ValuationMethod.balance],
    Category.other_liability: [ValuationMethod.model, ValuationMethod.balance, ValuationMethod.amortising],
}

DEFAULT_LIQUID: dict[Category, bool] = {
    Category.investment: True,
    Category.pension: False,
    Category.cash: True,
    Category.property: False,
    Category.mortgage: False,
    Category.loan: True,
    Category.credit_card: True,
    Category.other_asset: False,
    Category.other_liability: True,
}

METHODS_NOT_YET_SUPPORTED: set[ValuationMethod] = set()

LOAN_CATEGORIES = {Category.mortgage, Category.loan, Category.other_liability}

ILLIQUID_WRAPPERS = {Wrapper.lisa, Wrapper.jisa}
WRAPPED_SINGLE_OWNER = {
    Wrapper.isa,
    Wrapper.lisa,
    Wrapper.jisa,
    Wrapper.sipp,
    Wrapper.workplace_pension,
    Wrapper.db_pension,
}

SHARE_TOLERANCE = 1e-6


def default_is_liquid(category: Category, wrapper: Wrapper) -> bool:
    if wrapper in ILLIQUID_WRAPPERS:
        return False
    return DEFAULT_LIQUID[category]


def default_include_in_networth(wrapper: Wrapper, valuation_method: ValuationMethod) -> bool:
    # A DB pension entered as a bare balance stays out by default (docs/02-data-model.md); one set
    # up with scheme details has a capitalised value, which counts like any other pension.
    return wrapper != Wrapper.db_pension or valuation_method == ValuationMethod.defined_benefit


def validate_combination(
    category: Category, wrapper: Wrapper, valuation_method: ValuationMethod
) -> None:
    if wrapper not in ALLOWED_WRAPPERS[category]:
        raise DomainError(
            "validation", f"{wrapper.value} is not a valid wrapper for {category.value} accounts", field="wrapper"
        )
    if wrapper == Wrapper.db_pension and valuation_method not in (
        ValuationMethod.balance,
        ValuationMethod.defined_benefit,
    ):
        raise DomainError(
            "validation",
            "Defined-benefit pensions use the defined_benefit or balance valuation method",
            field="valuation_method",
        )
    if valuation_method == ValuationMethod.defined_benefit and wrapper != Wrapper.db_pension:
        raise DomainError(
            "validation",
            "The defined_benefit valuation method is only for db_pension accounts",
            field="valuation_method",
        )
    if valuation_method not in ALLOWED_METHODS[category]:
        raise DomainError(
            "validation",
            f"{valuation_method.value} is not a valid valuation method for {category.value} accounts",
            field="valuation_method",
        )
    if valuation_method in METHODS_NOT_YET_SUPPORTED:
        raise DomainError(
            "validation",
            f"{valuation_method.value} accounts are not supported yet",
            field="valuation_method",
        )


def validate_owners(wrapper: Wrapper, owners: Sequence[OwnerShareIn]) -> None:
    if not owners:
        raise DomainError("validation", "At least one owner is required", field="owners")

    if wrapper in WRAPPED_SINGLE_OWNER:
        if len(owners) != 1 or abs(owners[0].share - 1.0) > SHARE_TOLERANCE:
            raise DomainError(
                "validation",
                f"{wrapper.value} accounts must have exactly one owner with a 100% share",
                field="owners",
            )
        return

    total = sum(o.share for o in owners)
    if abs(total - 1.0) > SHARE_TOLERANCE:
        raise DomainError("validation", "Owner shares must sum to 100%", field="owners")


def validate_sub_objects(payload: AccountCreate) -> None:
    if payload.category == Category.property and payload.property is None:
        raise DomainError("validation", "Property accounts require property details", field="property")
    if payload.category != Category.property and payload.property is not None:
        raise DomainError(
            "validation", "Property details are only valid for property accounts", field="property"
        )
    if payload.valuation_method == ValuationMethod.model and payload.growth_model is None:
        raise DomainError(
            "validation", "Model-valued accounts require a growth model", field="growth_model"
        )
    if payload.valuation_method != ValuationMethod.model and payload.growth_model is not None:
        raise DomainError(
            "validation",
            "A growth model is only valid for accounts using the model valuation method",
            field="growth_model",
        )
    if payload.valuation_method == ValuationMethod.holdings and payload.initial_balance is not None:
        raise DomainError(
            "validation",
            "Holdings accounts get their value from transactions, not a balance entry",
            field="initial_balance",
        )
    if payload.valuation_method == ValuationMethod.amortising and payload.loan is None:
        raise DomainError(
            "validation", "Amortising accounts require loan details", field="loan"
        )
    if payload.valuation_method != ValuationMethod.amortising and payload.loan is not None:
        raise DomainError(
            "validation",
            "Loan details are only valid for accounts using the amortising valuation method",
            field="loan",
        )
    if payload.loan is not None and payload.category not in LOAN_CATEGORIES:
        raise DomainError(
            "validation", "Loan details are only valid for mortgage/loan/other_liability accounts", field="loan"
        )
    if payload.valuation_method == ValuationMethod.defined_benefit and payload.db_pension is None:
        raise DomainError(
            "validation", "Defined-benefit pensions require scheme details", field="db_pension"
        )
    if payload.valuation_method != ValuationMethod.defined_benefit and payload.db_pension is not None:
        raise DomainError(
            "validation",
            "Scheme details are only valid for accounts using the defined_benefit valuation method",
            field="db_pension",
        )
    if payload.loan is not None:
        overlap_check: list[LoanRatePeriod] = []
        for rp in payload.loan.rate_periods:
            fake = LoanRatePeriod(start_date=rp.start_date, end_date=rp.end_date)
            loan_service.validate_no_overlap(overlap_check, rp.start_date, rp.end_date)
            overlap_check.append(fake)


def _check_owners_exist(db: Session, owners: Sequence[OwnerShareIn]) -> None:
    person_ids = {o.person_id for o in owners}
    found_ids = set(db.scalars(select(Person.id).where(Person.id.in_(person_ids))).all())
    missing = person_ids - found_ids
    if missing:
        raise DomainError("validation", f"Unknown people: {sorted(missing)}", field="owners")


# ---------------------------------------------------------------------------
# Property purchase anchor
#
# docs/06-imports-future.md: "Property: purchase price at purchase date plus valuations; growth
# model fills between them." The purchase price/date on PropertyDetails is therefore not just
# reference data — it is the first point of the property's history. Persisting it as a
# `valuation` BalanceEntry is what lets _value_model() grow it forward to the next valuation, so
# snapshots (and the Property chart) start at completion rather than at account-creation day.
# ---------------------------------------------------------------------------

PurchaseAnchor = tuple[date, float]


def _purchase_anchor(details: PropertyDetailsIn | PropertyDetails | None) -> PurchaseAnchor | None:
    """The (date, price) anchor implied by property details, or None when either half is missing."""
    if details is None or details.purchase_date is None or details.purchase_price_gbp is None:
        return None
    return details.purchase_date, round(details.purchase_price_gbp, 2)


def _balance_entry_on(db: Session, account_id: int, on: date) -> BalanceEntry | None:
    return db.scalars(
        select(BalanceEntry).where(BalanceEntry.account_id == account_id, BalanceEntry.date == on)
    ).first()


def _is_our_anchor(entry: BalanceEntry, anchor: PurchaseAnchor) -> bool:
    """True when `entry` is the anchor this service wrote for `anchor` — a `valuation` entry at
    that date for that amount — and so is ours to move or re-price. A `manual`/`statement` entry,
    or one the owner has since edited to a different figure, is theirs and is never overwritten."""
    return entry.source == BalanceSource.valuation and abs(entry.balance_gbp - anchor[1]) <= 0.005


def _sync_purchase_anchor(
    db: Session, account_id: int, previous: PurchaseAnchor | None, new: PurchaseAnchor | None
) -> date | None:
    """Move/add/re-price the purchase anchor entry after property details change.

    Returns the earliest date touched (so the caller can rebuild snapshots from it), or None when
    nothing changed. Adds to the session but does not commit.
    """
    # Deliberately no "details unchanged, nothing to do" short-circuit: an account created before
    # the anchor existed already records the right purchase date and price, and re-saving those
    # details unchanged is exactly how such an account gets repaired.
    touched: list[date] = []

    # The old anchor becomes wrong when the purchase date moves — retire it, but only while it is
    # still recognisably ours, so a correction can't silently delete a real valuation.
    if previous is not None and (new is None or new[0] != previous[0]):
        old_entry = _balance_entry_on(db, account_id, previous[0])
        if old_entry is not None and _is_our_anchor(old_entry, previous):
            db.delete(old_entry)
            touched.append(previous[0])

    if new is not None:
        entry = _balance_entry_on(db, account_id, new[0])
        if entry is None:
            db.add(
                BalanceEntry(
                    account_id=account_id,
                    date=new[0],
                    balance_gbp=new[1],
                    source=BalanceSource.valuation,
                )
            )
            touched.append(new[0])
        elif (
            previous is not None
            and _is_our_anchor(entry, previous)
            and abs(entry.balance_gbp - new[1]) > 0.005
        ):
            entry.balance_gbp = new[1]
            touched.append(new[0])
        # else: the owner already has an entry on that date (their own valuation, or the account's
        # opening balance). Theirs wins — we leave it and let it act as the anchor.

    return min(touched) if touched else None


def create_account(db: Session, payload: AccountCreate) -> Account:
    validate_combination(payload.category, payload.wrapper, payload.valuation_method)
    validate_owners(payload.wrapper, payload.owners)
    validate_sub_objects(payload)
    _check_owners_exist(db, payload.owners)

    is_liquid = (
        payload.is_liquid
        if payload.is_liquid is not None
        else default_is_liquid(payload.category, payload.wrapper)
    )
    include_in_networth = (
        payload.include_in_networth
        if payload.include_in_networth is not None
        else default_include_in_networth(payload.wrapper, payload.valuation_method)
    )

    account = Account(
        name=payload.name,
        category=payload.category,
        wrapper=payload.wrapper,
        valuation_method=payload.valuation_method,
        provider=payload.provider,
        include_in_networth=include_in_networth,
        is_liquid=is_liquid,
        expected_return_rate=payload.expected_return_rate,
        annual_fee_rate=payload.annual_fee_rate,
        interest_rate=payload.interest_rate,
        opened_date=payload.opened_date,
        notes=payload.notes,
    )
    db.add(account)
    db.flush()

    for owner in payload.owners:
        db.add(AccountOwner(account_id=account.id, person_id=owner.person_id, share=owner.share))

    if payload.growth_model is not None:
        db.add(GrowthModel(account_id=account.id, **payload.growth_model.model_dump()))

    if payload.property is not None:
        db.add(PropertyDetails(account_id=account.id, **payload.property.model_dump()))

    if payload.loan is not None:
        loan_data = payload.loan.model_dump(exclude={"rate_periods"})
        db.add(LoanDetails(account_id=account.id, **loan_data))
        for rp in payload.loan.rate_periods:
            db.add(LoanRatePeriod(account_id=account.id, **rp.model_dump()))

    if payload.db_pension is not None:
        db_pension_service.upsert(db, account, payload.db_pension)

    if payload.initial_balance is not None:
        db.add(
            BalanceEntry(
                account_id=account.id,
                date=payload.initial_balance.date,
                balance_gbp=round(payload.initial_balance.balance_gbp, 2),
                source=payload.initial_balance.source,
            )
        )

    purchase_anchor = _purchase_anchor(payload.property)
    if purchase_anchor is not None:
        anchor_date, anchor_price = purchase_anchor
        # A property bought in the past and given a current value today gets two anchors: the
        # growth model fills between them and the later valuation takes over from its own date.
        # An initial_balance dated on the purchase date is the owner's own figure, so it stands.
        if payload.initial_balance is None or payload.initial_balance.date != anchor_date:
            db.add(
                BalanceEntry(
                    account_id=account.id,
                    date=anchor_date,
                    balance_gbp=anchor_price,
                    source=BalanceSource.valuation,
                )
            )

    db.commit()
    db.refresh(account)

    from app.services import projection_service

    # Rebuild from the earliest thing that gives the account a value. Amortising loan/mortgage
    # accounts have no initial_balance (their value is derived from loan terms, not a stored
    # balance), and a property's purchase predates its first valuation — without this they'd have
    # no AccountSnapshot rows before account-creation day until the next nightly catch_up, leaving
    # history/chart endpoints with nothing to show (docs/05-ui.md "history solid, future dashed").
    rebuild_from = [
        d
        for d in (
            payload.initial_balance.date if payload.initial_balance is not None else None,
            purchase_anchor[0] if purchase_anchor is not None else None,
            payload.loan.start_date if payload.loan is not None else None,
            payload.db_pension.accrued_as_of if payload.db_pension is not None else None,
        )
        if d is not None
    ]
    if rebuild_from:
        from app.services import snapshot_service

        snapshot_service.request_rebuild(account.id, min(rebuild_from))
    projection_service.bump_data_version()
    return account


def update_account(db: Session, account: Account, payload: AccountUpdate) -> Account:
    update_data = payload.model_dump(exclude_unset=True, exclude={"owners"})
    for field, value in update_data.items():
        setattr(account, field, value)

    if payload.owners is not None:
        validate_owners(account.wrapper, payload.owners)
        _check_owners_exist(db, payload.owners)
        account.owners.clear()
        db.flush()
        for owner in payload.owners:
            account.owners.append(AccountOwner(person_id=owner.person_id, share=owner.share))

    db.commit()
    db.refresh(account)

    from app.services import projection_service

    projection_service.bump_data_version()
    return account


def get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    return account


def list_accounts(
    db: Session,
    person_id: int | None = None,
    category: Category | None = None,
    include_archived: bool = False,
) -> list[Account]:
    query = select(Account)
    if not include_archived:
        query = query.where(Account.is_archived.is_(False))
    if category is not None:
        query = query.where(Account.category == category)
    if person_id is not None:
        query = query.join(AccountOwner).where(AccountOwner.person_id == person_id)
    query = query.order_by(Account.sort_order, Account.name)
    return list(db.scalars(query).unique().all())


def set_archived(db: Session, account: Account, archived: bool) -> Account:
    account.is_archived = archived
    db.commit()
    db.refresh(account)

    from app.services import projection_service

    projection_service.bump_data_version()
    return account


def delete_account(db: Session, account: Account) -> None:
    # Deletion is the only removal action in the UI, so an account is always deletable: its
    # history (balance entries, transactions, snapshots, positions, loan/property/growth detail,
    # recurring plans, ownership rows) goes with it via the ORM cascades and the FK
    # `ondelete="CASCADE"` rules (SQLite runs them; `PRAGMA foreign_keys=ON` is set in app/db.py).
    account_id = account.id
    db.delete(account)
    db.commit()
    # The broker link row cascades with the account; its API key lives outside the database.
    from app.services import broker_secrets

    broker_secrets.delete("trading212", account_id)

    from app.services import projection_service

    projection_service.bump_data_version()


def upsert_growth_model(db: Session, account: Account, payload: GrowthModelIn) -> GrowthModel:
    if account.valuation_method != ValuationMethod.model:
        raise DomainError(
            "validation",
            "A growth model only applies to accounts using the model valuation method",
            field="valuation_method",
        )
    gm = account.growth_model
    if gm is None:
        gm = GrowthModel(account_id=account.id)
        db.add(gm)
    for field, value in payload.model_dump().items():
        setattr(gm, field, value)
    db.commit()
    db.refresh(gm)

    # A new rate re-values every day from the account's *first* anchor onwards (a property bought
    # in 2022 and valued today has two), so rebuild from the earliest entry, not the latest.
    entry = valuation_service.earliest_balance_entry(db, account.id)
    if entry is not None:
        from app.services import snapshot_service

        snapshot_service.request_rebuild(account.id, entry.date)

    from app.services import projection_service

    projection_service.bump_data_version()
    return gm


def upsert_property_details(db: Session, account: Account, payload: PropertyDetailsIn) -> PropertyDetails:
    if account.category != Category.property:
        raise DomainError(
            "validation", "Property details only apply to property accounts", field="category"
        )
    details = account.property_details
    previous_anchor = _purchase_anchor(details)
    if details is None:
        details = PropertyDetails(account_id=account.id)
        db.add(details)
    for field, value in payload.model_dump().items():
        setattr(details, field, value)

    rebuild_from = _sync_purchase_anchor(db, account.id, previous_anchor, _purchase_anchor(payload))
    db.commit()
    db.refresh(details)

    from app.services import projection_service, snapshot_service

    if rebuild_from is not None:
        snapshot_service.request_rebuild(account.id, rebuild_from)
        projection_service.bump_data_version()
    return details


def upsert_loan_details(db: Session, account: Account, payload: LoanDetailsIn) -> LoanDetails:
    if account.valuation_method != ValuationMethod.amortising:
        raise DomainError(
            "validation",
            "Loan details only apply to accounts using the amortising valuation method",
            field="valuation_method",
        )
    ld = account.loan_details
    if ld is None:
        ld = LoanDetails(account_id=account.id)
        db.add(ld)
    for field, value in payload.model_dump().items():
        setattr(ld, field, value)
    db.commit()
    db.refresh(ld)

    entry = valuation_service.latest_balance_entry(db, account.id, date_today())
    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account.id, entry.date if entry else date_today())
    projection_service.bump_data_version()
    return ld


def upsert_db_pension_details(db: Session, account: Account, payload: DbPensionDetailsIn):
    if account.valuation_method != ValuationMethod.defined_benefit:
        raise DomainError(
            "validation",
            "Scheme details only apply to accounts using the defined_benefit valuation method",
            field="valuation_method",
        )
    details = db_pension_service.upsert(db, account, payload)
    db.commit()
    db.refresh(details)

    from app.services import projection_service, snapshot_service

    snapshot_service.request_rebuild(account.id, details.accrued_as_of)
    projection_service.bump_data_version()
    return details


def build_account_summary(
    db: Session, account: Account, on: date, person_ids: set[int] | None
) -> AccountSummary:
    valuation = valuation_service.value_account(db, account, on, live=True)
    scoped = (
        valuation_service.scoped_value(valuation.value_gbp, account, person_ids)
        if person_ids is not None
        else valuation.value_gbp
    )

    gain_gbp = gain_pct = day_change_pct = None
    last_updated = None
    if account.valuation_method == ValuationMethod.holdings:
        if valuation.cost_basis_gbp is not None:
            gain_gbp = round(valuation.value_gbp - valuation.cost_basis_gbp, 2)
            gain_pct = gain_gbp / valuation.cost_basis_gbp if valuation.cost_basis_gbp else None
        if valuation.day_change_gbp is not None:
            prev_value = valuation.value_gbp - valuation.day_change_gbp
            day_change_pct = valuation.day_change_gbp / prev_value if prev_value else None
        positions = db.scalars(select(Position).where(Position.account_id == account.id)).all()
        last_price_ats = [p.instrument.last_price_at for p in positions if p.instrument.last_price_at]
        last_updated = max(last_price_ats) if last_price_ats else None
    else:
        last_entry = valuation_service.latest_balance_entry(db, account.id, on)
        last_updated = last_entry.updated_at if last_entry else None

    return AccountSummary(
        id=account.id,
        name=account.name,
        category=account.category,
        wrapper=account.wrapper,
        valuation_method=account.valuation_method,
        provider=account.provider,
        owners=[
            OwnerShareOut(
                person_id=o.person_id, name=o.person.name, color=o.person.color, share=o.share
            )
            for o in account.owners
        ],
        value_gbp=valuation.value_gbp,
        scoped_value_gbp=scoped,
        cost_basis_gbp=valuation.cost_basis_gbp,
        gain_gbp=gain_gbp,
        gain_pct=gain_pct,
        day_change_gbp=valuation.day_change_gbp,
        day_change_pct=day_change_pct,
        is_liability=account.category in valuation_service.LIABILITY_CATEGORIES,
        is_liquid=account.is_liquid,
        include_in_networth=account.include_in_networth,
        is_estimated=valuation.is_estimated,
        is_archived=account.is_archived,
        last_updated=last_updated,
        staleness=valuation_service.staleness(db, account, on),
        days_since_update=valuation_service.days_since_update(db, account, on),
        detail=valuation.detail,
    )


def build_account_detail(db: Session, account: Account, on: date) -> AccountDetail:
    summary = build_account_summary(db, account, on, person_ids=None)
    return AccountDetail(
        **summary.model_dump(),
        expected_return_rate=account.expected_return_rate,
        annual_fee_rate=account.annual_fee_rate,
        interest_rate=account.interest_rate,
        opened_date=account.opened_date,
        closed_date=account.closed_date,
        notes=account.notes,
        growth_model=GrowthModelOut.model_validate(account.growth_model) if account.growth_model else None,
        property=PropertyDetailsOut.model_validate(account.property_details)
        if account.property_details
        else None,
        loan=LoanDetailsOut.model_validate(account.loan_details) if account.loan_details else None,
        db_pension=DbPensionDetailsOut.model_validate(account.db_pension_details)
        if account.db_pension_details
        else None,
        db_pension_summary=db_pension_service.summary(db, account) if account.db_pension_details else None,
        broker_sync=link.provider if (link := db.get(BrokerLink, account.id)) is not None else None,
    )
