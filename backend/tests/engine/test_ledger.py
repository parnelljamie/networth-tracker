from datetime import date

import pytest

from app.engine.ledger import (
    LedgerError,
    Txn,
    apply,
    cash_target_adjustment,
    position_target_adjustment,
    replay,
    replay_series,
    validate_txn,
)

D = date(2026, 1, 1)
VUSA, VWRP = 1, 2


def test_average_cost_through_buys_and_sells():
    txns = [
        Txn(D, "DEPOSIT", amount_gbp=5_000, id=1),
        Txn(D, "OPENING_BALANCE", VUSA, units=100, cost_basis_gbp=8_000, id=2),
        Txn(date(2026, 2, 1), "BUY", VUSA, units=50, amount_gbp=-4_600, id=3),
        Txn(date(2026, 3, 1), "SELL", VUSA, units=30, amount_gbp=3_000, id=4),
    ]
    s = replay(txns, strict=True)
    p = s.positions[VUSA]
    assert p.units == 120
    assert p.cost_gbp == pytest.approx(10_080)
    assert p.avg_cost_gbp == pytest.approx(84)
    assert p.realised_gain_gbp == pytest.approx(480)
    assert p.first_date == D
    assert s.cash_gbp == pytest.approx(3_400)
    assert s.net_contributions_gbp == 5_000


def test_income_and_charges():
    s = replay(
        [
            Txn(D, "DIVIDEND", amount_gbp=50),
            Txn(D, "INTEREST", amount_gbp=5),
            Txn(D, "FEE", amount_gbp=-10),
            Txn(D, "TAX", amount_gbp=-2),
        ]
    )
    assert s.income_gbp == 55
    assert s.fees_gbp == 12
    assert s.cash_gbp == pytest.approx(43)


def test_same_day_buy_is_applied_before_sell():
    s = replay(
        [
            Txn(D, "SELL", VWRP, units=5, amount_gbp=500, id=1),
            Txn(D, "BUY", VWRP, units=10, amount_gbp=-900, id=2),
        ],
        strict=True,
    )
    assert s.positions[VWRP].units == 5
    assert not s.warnings


def test_oversell_warns_or_raises():
    txns = [
        Txn(D, "BUY", VWRP, units=10, amount_gbp=-900),
        Txn(date(2026, 2, 1), "SELL", VWRP, units=15, amount_gbp=1_500),
    ]
    s = replay(txns)
    assert s.positions[VWRP].units == 0
    assert len(s.warnings) == 1
    assert s.realised_gain_gbp == pytest.approx(1_000 - 900)  # proceeds scaled to units held
    with pytest.raises(LedgerError):
        replay(txns, strict=True)


def test_split_keeps_cost():
    s = replay(
        [
            Txn(D, "BUY", VUSA, units=10, amount_gbp=-1_000),
            Txn(date(2026, 6, 1), "SPLIT", VUSA, split_ratio=10),
        ]
    )
    assert s.positions[VUSA].units == 100
    assert s.positions[VUSA].avg_cost_gbp == pytest.approx(10)


def test_transfer_out_removes_at_average_cost_without_gain():
    s = replay(
        [
            Txn(D, "BUY", VUSA, units=10, amount_gbp=-1_000),
            Txn(date(2026, 3, 1), "TRANSFER_OUT", VUSA, units=4),
        ]
    )
    assert s.positions[VUSA].units == 6
    assert s.positions[VUSA].cost_gbp == pytest.approx(600)
    assert s.realised_gain_gbp == 0


def test_validation_rejects_wrong_signs_and_missing_fields():
    for bad in [
        Txn(D, "BUY", VUSA, units=1, amount_gbp=100),
        Txn(D, "WITHDRAWAL", amount_gbp=100),
        Txn(D, "SELL", None, units=1, amount_gbp=100),
        Txn(D, "SPLIT", VUSA),
        Txn(D, "NOPE"),
    ]:
        with pytest.raises(LedgerError):
            validate_txn(bad)


def test_replay_as_of_and_series_are_independent_snapshots():
    txns = [
        Txn(date(2026, 1, 1), "BUY", VUSA, units=10, amount_gbp=-1_000),
        Txn(date(2026, 1, 3), "BUY", VUSA, units=5, amount_gbp=-600),
    ]
    assert replay(txns, as_of=date(2026, 1, 2)).positions[VUSA].units == 10
    days = [date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    series = replay_series(txns, days)
    assert [st.positions[VUSA].units if VUSA in st.positions else 0 for st in series] == [0, 10, 10, 15]
    series[1].positions[VUSA].units = 999
    assert series[2].positions[VUSA].units == 10


def test_editing_a_holding_becomes_an_adjustment():
    state = replay(
        [
            Txn(D, "OPENING_BALANCE", VUSA, units=120, cost_basis_gbp=10_080),
            Txn(D, "DEPOSIT", amount_gbp=50),
        ]
    )
    du, dc = position_target_adjustment(state, VUSA, target_units=125, target_avg_cost_gbp=85)
    assert du == pytest.approx(5)
    assert dc == pytest.approx(545)
    apply(state, Txn(date(2026, 9, 15), "ADJUSTMENT", VUSA, units=du, cost_basis_gbp=dc))
    assert state.positions[VUSA].units == pytest.approx(125)
    assert state.positions[VUSA].avg_cost_gbp == pytest.approx(85)

    apply(state, Txn(date(2026, 9, 15), "ADJUSTMENT", amount_gbp=cash_target_adjustment(state, 20)))
    assert state.cash_gbp == pytest.approx(20)

    assert position_target_adjustment(state, VWRP, 10, 100) == (10, 1_000)
    with pytest.raises(LedgerError):
        position_target_adjustment(state, VWRP, -1, 100)


def test_share_transfers_move_net_contributions_at_cost():
    # An ISA transfer in specie: 99 units leave one account at its average cost and arrive in
    # the other with the same cost basis. The money behind them moves with them.
    old = replay(
        [
            Txn(D, "DEPOSIT", amount_gbp=6_000, id=1),
            Txn(D, "BUY", VUSA, units=100, amount_gbp=-5_386, id=2),
            Txn(date(2026, 8, 26), "TRANSFER_OUT", VUSA, units=99, id=3),
        ],
        strict=True,
    )
    assert old.net_contributions_gbp == pytest.approx(6_000 - 5_332.14)
    assert old.cash_gbp == pytest.approx(614)

    new = replay(
        [
            Txn(date(2026, 8, 26), "TRANSFER_IN", VUSA, units=99, cost_basis_gbp=5_332.14, id=1),
            Txn(date(2026, 9, 1), "TRANSFER_IN", amount_gbp=2_953.28, id=2),
        ],
        strict=True,
    )
    assert new.net_contributions_gbp == pytest.approx(5_332.14 + 2_953.28)
    assert new.cash_gbp == pytest.approx(2_953.28)
