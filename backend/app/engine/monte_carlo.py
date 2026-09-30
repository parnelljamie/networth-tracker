"""Monte Carlo range of outcomes around the deterministic projection (docs/03-domain-logic.md §10).

Only growth accounts with market risk are simulated; everything else (property and other model
assets, loans, DB pensions, static items, cash) takes its deterministic path from `project()`, so
the median sits close to — slightly below — the deterministic line and the band shows market risk
alone.

Per simulated account and interval of `dt` years:

    log-return = ln(1 + r) * dt - sigma_a^2 * dt / 2 + sqrt(dt) * sum_c(w_c * sigma_c * Z_c)

where `r` is the same rate the deterministic model uses (scenario adjustment and rate changes
included, fee deducted), `w_c` the account's asset-class weights, `sigma_c` the class volatility
and `sigma_a^2 = sum_c (w_c * sigma_c)^2`. The `-sigma^2/2` term makes the *mean* growth equal
the deterministic growth. One draw `Z_c` per asset class per interval is shared by every account,
so equity accounts move together; classes are drawn independently of each other. Contributions,
withdrawals and lump sums land exactly as in the deterministic model, and values never go below
zero.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from .dates import years_between
from .growth import growth_factor
from .projection import (
    Assumptions,
    LumpSum,
    ProjectionAccount,
    ProjectionFlow,
    RateChange,
    _growth_series,
    project,
)

PERCENTILES = (10, 25, 50, 75, 90)


@dataclass
class MonteCarloResult:
    dates: list[date]
    percentiles: dict[int, list[float]]  # 10 -> p10 of the total at each date, ...
    deterministic: list[float]  # the plain projection's total, for reference
    paths: int


def _interval_rates(
    acct: ProjectionAccount, dates: Sequence[date], changes: list[RateChange], assumptions: Assumptions
) -> list[float]:
    """The annual rate applied over each interval, chosen exactly as `_growth_series` does."""
    ordered = sorted(changes, key=lambda c: c.date)
    adjustment = assumptions.return_adjustment if acct.scenario_adjustable else 0.0
    rates = []
    for m in range(1, len(dates)):
        base = acct.annual_rate
        for c in ordered:
            if c.date <= dates[m - 1]:
                base = c.annual_rate
        rates.append(base + adjustment - acct.annual_fee_rate)
    return rates


def simulate(
    accounts: Iterable[ProjectionAccount],
    flows: Iterable[ProjectionFlow],
    lump_sums: Iterable[LumpSum],
    today: date,
    months: int,
    risk_weights: Mapping[int, Mapping[str, float]],
    volatility: Mapping[str, float],
    assumptions: Assumptions | None = None,
    rate_changes: Iterable[RateChange] = (),
    person_id: int | None = None,
    paths: int = 1000,
    seed: int = 0,
) -> MonteCarloResult:
    """`risk_weights[account_id]` maps asset class -> weight (summing to 1) for each growth account
    to simulate; growth accounts without an entry, or with zero volatility, stay deterministic.
    `person_id` scopes the total to that person's ownership shares (None = household)."""
    assumptions = assumptions or Assumptions()
    accounts = list(accounts)
    flows = list(flows)
    lump_sums = list(lump_sums)
    rate_changes = list(rate_changes)

    base = project(accounts, flows, lump_sums, today, months, assumptions, rate_changes)
    dates = base.dates
    n = len(dates)

    def share(acct: ProjectionAccount) -> float:
        return 1.0 if person_id is None else acct.owners.get(person_id, 0.0)

    def sigma_of(acct_id: int) -> float:
        weights = risk_weights.get(acct_id, {})
        return math.sqrt(sum((w * volatility.get(c, 0.0)) ** 2 for c, w in weights.items()))

    simulated = [
        a
        for a in accounts
        if a.kind == "growth" and not a.is_liability and share(a) > 0 and sigma_of(a.id) > 0
    ]
    simulated_ids = {a.id for a in simulated}

    fixed = np.zeros(n)
    for acct in accounts:
        if acct.id not in simulated_ids and share(acct) > 0:
            fixed += np.asarray(base.by_account[acct.id]) * share(acct)
    deterministic = [round(float(x), 2) for x in fixed]
    for acct in simulated:
        for i, x in enumerate(base.by_account[acct.id]):
            deterministic[i] = round(deterministic[i] + x * share(acct), 2)

    totals = np.tile(fixed, (paths, 1))
    if simulated and n > 1:
        rng = np.random.default_rng(seed)
        classes = sorted({c for a in simulated for c in risk_weights[a.id]})
        shocks = {c: rng.standard_normal((paths, n - 1)) for c in classes}
        dt = np.array([years_between(dates[m - 1], dates[m]) for m in range(1, n)])
        deflators = np.array(
            [
                1.0 / growth_factor(assumptions.inflation_rate, years_between(today, d))
                if assumptions.real_terms
                else 1.0
                for d in dates
            ]
        )

        for acct in simulated:
            weights = risk_weights[acct.id]
            sigma = sigma_of(acct.id)
            _values, added = _growth_series(
                acct,
                dates,
                [f for f in flows if f.account_id == acct.id],
                [ls for ls in lump_sums if ls.account_id == acct.id],
                [c for c in rate_changes if c.account_id == acct.id],
                assumptions,
            )
            moves = np.diff(np.asarray(added))
            rates = _interval_rates(
                acct, dates, [c for c in rate_changes if c.account_id == acct.id], assumptions
            )
            # A rate of -100% or worse wipes the account out, as growth_factor does.
            drift = np.array([math.log1p(r) if r > -1 else -math.inf for r in rates]) * dt
            drift -= 0.5 * sigma**2 * dt
            noise = sum(weights[c] * volatility.get(c, 0.0) * shocks[c] for c in weights)
            log_returns = drift + np.sqrt(dt) * noise

            value = np.full(paths, acct.value)
            series = np.empty((paths, n))
            series[:, 0] = value
            for m in range(n - 1):
                value = np.maximum(value * np.exp(log_returns[:, m]) + moves[m], 0.0)
                series[:, m + 1] = value
            totals += series * deflators * share(acct)

    pct = np.percentile(totals, PERCENTILES, axis=0)
    return MonteCarloResult(
        dates=dates,
        percentiles={p: [round(float(x), 2) for x in row] for p, row in zip(PERCENTILES, pct, strict=True)},
        deterministic=deterministic,
        paths=paths,
    )
