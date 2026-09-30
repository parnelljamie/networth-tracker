"""docs/03-domain-logic.md §9 "Change attribution" (Phase 7).

For a period [start, end] and every in-scope account (household, or one person via
`AccountOwner.share`, mirroring `snapshot_service.total_on_or_before`), Δvalue is decomposed
per the account's valuation method/category:

- holdings accounts: `market = Δvalue − Δnet_contributions`, `contributions = Δnet_contributions`,
  where Δnet_contributions is the change in the ledger's net contributions over the period:
  deposits, withdrawals and transfers, with shares transferred in or out counted at cost (replayed
  from `transactions`, not read from the `account_snapshots.net_contributions_gbp` column — see
  judgement call below).
- cash (balance method): `contributions = Δvalue` (every balance movement is treated as money
  moved, since there is no ledger to separate market effects from a plain bank balance).
- loans/mortgages/credit cards/other liabilities (`valuation_service.LIABILITY_CATEGORIES`):
  `debt_paydown = Δvalue` (value is stored negative, so paying down debt is a positive delta).
  Exposed on the response as `mortgage_paid_gbp` per the BUILD_PLAN Phase 7 example ("+£610
  mortgage paid"), even though it also covers non-mortgage debt paydown — see judgement call.
- property/other `model`-valued accounts: `revaluation = Δvalue`.
- balance-method pensions (and any other balance-method account not covered above, e.g. a
  balance-valued investment/GIA): `other = Δvalue`.

Every in-scope account's Δvalue lands in exactly one bucket, so
`contributions + market + mortgage_paid + revaluation + other == end_total − start_total`
by construction — this is the identity the frontend's attribution card checks.

Judgement calls where the spec was ambiguous:
- "Nearest snapshot" for a date with no exact `account_snapshots` row uses the latest snapshot
  on or before that date (same rule as `snapshot_service.total_on_or_before`); an account with no
  snapshot at all on or before a date is treated as having value 0 then (e.g. it was opened
  partway through the period), so its whole opening value shows up as a Δvalue in whichever
  bucket it belongs to for that period.
- `account_snapshots.net_contributions_gbp` is written by both snapshot paths for holdings
  accounts: the ledger-replay path (`snapshot_service._backfill_holdings_account`) and
  `_write_snapshot`, which opts into `valuation_service.value_account(...,
  with_net_contributions=True)`. Non-holdings accounts still get `None`, and rows written before
  that fix keep their NULL until the account is rebuilt. This service therefore keeps recomputing
  Δnet_contributions from `transactions` (a ledger replay, since a share transfer's cost when it
  leaves is the average cost at that moment), so attribution does not depend on when a snapshot
  happened to be written.
- "Mortgage/loan liability paid down" bucket also picks up credit-card and other-liability
  balance/amortising accounts, since docs §9 only calls out one "loans" bucket generically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Category, ValuationMethod
from app.engine import ledger
from app.models.people import Person
from app.models.snapshots import AccountSnapshot
from app.schemas.attribution import AttributionOut
from app.services import account_service, ledger_service, valuation_service


@dataclass
class _Buckets:
    contributions: float = 0.0
    market: float = 0.0
    mortgage_paid: float = 0.0
    revaluation: float = 0.0
    other: float = 0.0
    start_total: float = 0.0
    end_total: float = 0.0


def _snapshot_value(db: Session, account_id: int, on: date) -> float:
    row = db.scalars(
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account_id, AccountSnapshot.date <= on)
        .order_by(AccountSnapshot.date.desc())
        .limit(1)
    ).first()
    return row.value_gbp if row is not None else 0.0


def _net_contributions(db: Session, account_id: int, start: date, end: date) -> float:
    txns = [ledger_service.to_engine_txn(r) for r in ledger_service.confirmed_txns(db, account_id)]
    before, after = ledger.replay_series(txns, [start, end])
    return after.net_contributions_gbp - before.net_contributions_gbp


def _scope_ids(db: Session, person_id: int | None) -> set[int]:
    if person_id is not None:
        return {person_id}
    people = list(db.scalars(select(Person).where(Person.is_archived.is_(False))).all())
    return {p.id for p in people if p.include_in_household}


def attribution(db: Session, start: date, end: date, person_id: int | None = None) -> AttributionOut:
    scope_ids = _scope_ids(db, person_id)
    accounts = [
        a for a in account_service.list_accounts(db, include_archived=False) if a.include_in_networth
    ]

    buckets = _Buckets()

    for account in accounts:
        share = sum(o.share for o in account.owners if o.person_id in scope_ids)
        if share <= 0:
            continue

        start_value = _snapshot_value(db, account.id, start) * share
        end_value = _snapshot_value(db, account.id, end) * share
        delta = end_value - start_value

        buckets.start_total += start_value
        buckets.end_total += end_value

        if account.valuation_method == ValuationMethod.holdings:
            net_contrib = _net_contributions(db, account.id, start, end) * share
            buckets.contributions += net_contrib
            buckets.market += delta - net_contrib
        elif account.category == Category.cash:
            buckets.contributions += delta
        elif account.category in valuation_service.LIABILITY_CATEGORIES:
            buckets.mortgage_paid += delta
        elif account.valuation_method in (ValuationMethod.model, ValuationMethod.defined_benefit):
            buckets.revaluation += delta
        else:
            buckets.other += delta

    total = (
        buckets.contributions + buckets.market + buckets.mortgage_paid + buckets.revaluation + buckets.other
    )

    return AttributionOut(
        start=start,
        end=end,
        person_id=person_id,
        start_total_gbp=round(buckets.start_total, 2),
        end_total_gbp=round(buckets.end_total, 2),
        contributions_gbp=round(buckets.contributions, 2),
        market_gbp=round(buckets.market, 2),
        mortgage_paid_gbp=round(buckets.mortgage_paid, 2),
        revaluation_gbp=round(buckets.revaluation, 2),
        other_gbp=round(buckets.other, 2),
        total_gbp=round(total, 2),
    )
