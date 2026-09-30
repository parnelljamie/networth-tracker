import math
from datetime import date

import pytest

from app.engine.amortisation import LoanTerms
from app.engine.monte_carlo import simulate
from app.engine.projection import Assumptions, ProjectionAccount, ProjectionFlow, project
from app.engine.recurring import Plan

TODAY = date(2026, 1, 1)
VOL = {"equity": 0.16, "bond": 0.06, "cash": 0.0}


def _isa(acct_id: int = 1, value: float = 100_000, owners: dict[int, float] | None = None) -> ProjectionAccount:
    return ProjectionAccount(
        acct_id, "investment", "growth", value, owners=owners or {1: 1.0}, annual_rate=0.06
    )


def test_zero_volatility_reproduces_the_deterministic_projection():
    acct = _isa()
    plan = Plan(500, "monthly", TODAY)
    flows = [ProjectionFlow(1, plan)]
    mc = simulate([acct], flows, [], TODAY, 24, {1: {"cash": 1.0}}, VOL, paths=50)
    det = project([acct], flows, [], TODAY, 24)
    for p in (10, 50, 90):
        assert mc.percentiles[p] == pytest.approx(det.total, abs=0.01)
    assert mc.deterministic == det.total


def test_percentiles_are_ordered_and_spread_out_over_time():
    mc = simulate([_isa()], [], [], TODAY, 120, {1: {"equity": 1.0}}, VOL, paths=2000)
    for i in range(len(mc.dates)):
        values = [mc.percentiles[p][i] for p in (10, 25, 50, 75, 90)]
        assert values == sorted(values)
    assert mc.percentiles[10][0] == mc.percentiles[90][0] == 100_000
    spread_1y = mc.percentiles[90][12] - mc.percentiles[10][12]
    spread_10y = mc.percentiles[90][120] - mc.percentiles[10][120]
    assert spread_10y > 2 * spread_1y


def test_median_follows_lognormal_maths():
    """With no flows, ln(value) is normal, so the median is value * (1 + r)^t * exp(-sigma^2 t / 2)."""
    mc = simulate([_isa()], [], [], TODAY, 120, {1: {"equity": 1.0}}, VOL, paths=20_000, seed=1)
    years = (mc.dates[120] - TODAY).days / 365.25
    expected = 100_000 * 1.06**years * math.exp(-0.5 * 0.16**2 * years)
    assert mc.percentiles[50][120] == pytest.approx(expected, rel=0.02)


def test_p10_and_p90_match_the_lognormal_quantiles():
    mc = simulate([_isa()], [], [], TODAY, 120, {1: {"equity": 1.0}}, VOL, paths=20_000, seed=2)
    years = (mc.dates[120] - TODAY).days / 365.25
    mu = math.log(100_000) + years * (math.log(1.06) - 0.5 * 0.16**2)
    z90 = 1.2815515655
    assert mc.percentiles[90][120] == pytest.approx(math.exp(mu + z90 * 0.16 * math.sqrt(years)), rel=0.03)
    assert mc.percentiles[10][120] == pytest.approx(math.exp(mu - z90 * 0.16 * math.sqrt(years)), rel=0.03)


def test_same_asset_class_accounts_move_together():
    """One shared draw per class per month: two equity ISAs behave like one account of their
    combined size, so the band is as wide as a single account's, not narrowed by diversification."""
    two = simulate(
        [_isa(1, 50_000), _isa(2, 50_000)], [], [], TODAY, 60, {1: {"equity": 1.0}, 2: {"equity": 1.0}}, VOL, paths=500
    )
    one = simulate([_isa(1, 100_000)], [], [], TODAY, 60, {1: {"equity": 1.0}}, VOL, paths=500)
    for p in (10, 50, 90):
        assert two.percentiles[p][60] == pytest.approx(one.percentiles[p][60], abs=0.05)


def test_mixed_account_is_less_volatile_than_all_equity():
    equity = simulate([_isa()], [], [], TODAY, 120, {1: {"equity": 1.0}}, VOL, paths=2000)
    mixed = simulate([_isa()], [], [], TODAY, 120, {1: {"equity": 0.6, "bond": 0.4}}, VOL, paths=2000)
    width = lambda r: r.percentiles[90][120] - r.percentiles[10][120]  # noqa: E731
    assert width(mixed) < width(equity)


def test_deterministic_accounts_add_their_plain_path_to_every_percentile():
    terms = LoanTerms(maturity=date(2051, 1, 1), fallback_rate=0.045)
    mortgage = ProjectionAccount(2, "mortgage", "loan", 200_000, owners={1: 1.0}, loan_terms=terms)
    house = ProjectionAccount(3, "property", "model", 300_000, owners={1: 1.0}, annual_rate=0.03)
    accounts = [_isa(), mortgage, house]
    risky = simulate(accounts, [], [], TODAY, 60, {1: {"equity": 1.0}}, VOL, paths=500)
    isa_only = simulate([_isa()], [], [], TODAY, 60, {1: {"equity": 1.0}}, VOL, paths=500)
    det = project([mortgage, house], [], [], TODAY, 60)
    for i in (0, 12, 60):
        assert risky.percentiles[50][i] == pytest.approx(isa_only.percentiles[50][i] + det.total[i], abs=0.05)


def test_person_scope_uses_ownership_shares():
    joint = _isa(owners={1: 0.5, 2: 0.5})
    household = simulate([joint], [], [], TODAY, 36, {1: {"equity": 1.0}}, VOL, paths=500)
    person = simulate([joint], [], [], TODAY, 36, {1: {"equity": 1.0}}, VOL, person_id=1, paths=500)
    other = simulate([joint], [], [], TODAY, 36, {1: {"equity": 1.0}}, VOL, person_id=3, paths=500)
    assert person.percentiles[50][36] == pytest.approx(household.percentiles[50][36] / 2, abs=0.05)
    assert other.percentiles[90][36] == 0


def test_withdrawals_never_push_a_path_below_zero():
    plan = Plan(2_000, "monthly", TODAY)
    flows = [ProjectionFlow(1, plan, kind="withdrawal")]
    mc = simulate([_isa(value=50_000)], flows, [], TODAY, 60, {1: {"equity": 1.0}}, VOL, paths=500)
    assert min(mc.percentiles[10]) >= 0
    assert mc.percentiles[50][60] == 0


def test_same_seed_gives_the_same_result():
    a = simulate([_isa()], [], [], TODAY, 24, {1: {"equity": 1.0}}, VOL, paths=200, seed=7)
    b = simulate([_isa()], [], [], TODAY, 24, {1: {"equity": 1.0}}, VOL, paths=200, seed=7)
    assert a.percentiles == b.percentiles


def test_real_terms_deflates_the_band():
    nominal = simulate([_isa()], [], [], TODAY, 120, {1: {"equity": 1.0}}, VOL, paths=500)
    real = simulate(
        [_isa()], [], [], TODAY, 120, {1: {"equity": 1.0}}, VOL, Assumptions(real_terms=True), paths=500
    )
    years = (real.dates[120] - TODAY).days / 365.25
    assert real.percentiles[50][120] == pytest.approx(nominal.percentiles[50][120] / 1.025**years, rel=1e-6)
