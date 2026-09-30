"""Investment ledger: transactions -> positions (average cost), cash and flow totals.

`amount_gbp` is always the signed cash effect on the account. Effects per type:

| type            | units              | cost basis                  | cash         | notes                         |
|-----------------|--------------------|-----------------------------|--------------|-------------------------------|
| OPENING_BALANCE | +units (instrument)| +cost_basis_gbp             | +amount      | cash row when no instrument   |
| BUY             | +units             | += -amount (incl. fees)     | amount (< 0) |                               |
| SELL            | -units             | -= avg_cost * units         | amount (> 0) | realised += amount - removed  |
| DEPOSIT         |                    |                             | amount (> 0) | net contributions += amount   |
| WITHDRAWAL      |                    |                             | amount (< 0) | net contributions += amount   |
| DIVIDEND        |                    |                             | amount (> 0) | income                        |
| INTEREST        |                    |                             | amount (> 0) | income                        |
| FEE / TAX       |                    |                             | amount (< 0) | fees                          |
| TRANSFER_IN     | +units (instrument)| +cost_basis_gbp             | +amount      | contribution += amount + cost |
| TRANSFER_OUT    | -units (instrument)| -= avg_cost * units         | amount (< 0) | contribution += amount - cost |
| SPLIT           | *= split_ratio     | unchanged                   |              |                               |
| ADJUSTMENT      | += units (signed)  | += cost_basis_gbp (signed)  | +amount      | manual corrections            |

Shares transferred in or out without cash (e.g. an ISA transfer in specie) move net contributions
at cost: the cost basis they arrive with, or the average cost they leave at. Otherwise the money
behind them would stay counted in the old account and never show in the new one.

Same-day ordering: opening balances, then money in, splits, buys, adjustments, income, sells,
charges, money out, then insertion order (`id`). Callers pass confirmed transactions only.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

EPS_UNITS = 1e-9

TYPE_ORDER = {
    "OPENING_BALANCE": 0,
    "DEPOSIT": 1,
    "TRANSFER_IN": 1,
    "SPLIT": 2,
    "BUY": 3,
    "ADJUSTMENT": 4,
    "DIVIDEND": 5,
    "INTEREST": 5,
    "SELL": 6,
    "FEE": 7,
    "TAX": 7,
    "WITHDRAWAL": 8,
    "TRANSFER_OUT": 8,
}

_UNIT_TYPES = {"BUY", "SELL", "SPLIT"}


class LedgerError(ValueError):
    """A transaction is malformed or impossible (e.g. selling more than is held in strict mode)."""


@dataclass(frozen=True)
class Txn:
    date: date
    type: str
    instrument_id: int | None = None
    units: float = 0.0
    amount_gbp: float = 0.0
    cost_basis_gbp: float = 0.0
    split_ratio: float | None = None
    id: int = 0


@dataclass
class Position:
    units: float = 0.0
    cost_gbp: float = 0.0
    realised_gain_gbp: float = 0.0
    first_date: date | None = None

    @property
    def avg_cost_gbp(self) -> float:
        return self.cost_gbp / self.units if self.units > EPS_UNITS else 0.0


@dataclass
class LedgerState:
    positions: dict[int, Position] = field(default_factory=dict)
    cash_gbp: float = 0.0
    net_contributions_gbp: float = 0.0  # deposits + transfers in (cash, shares at cost) - money/shares out
    income_gbp: float = 0.0
    fees_gbp: float = 0.0
    realised_gain_gbp: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def copy(self) -> LedgerState:
        return LedgerState(
            positions={k: replace(v) for k, v in self.positions.items()},
            cash_gbp=self.cash_gbp,
            net_contributions_gbp=self.net_contributions_gbp,
            income_gbp=self.income_gbp,
            fees_gbp=self.fees_gbp,
            realised_gain_gbp=self.realised_gain_gbp,
            warnings=list(self.warnings),
        )

    def held(self) -> dict[int, Position]:
        """Positions with a non-zero unit balance."""
        return {k: v for k, v in self.positions.items() if v.units > EPS_UNITS}


def validate_txn(t: Txn) -> None:
    """Raise LedgerError when a transaction breaks the sign/field rules in the module docstring."""
    kind, has_inst = t.type, t.instrument_id is not None

    def fail(msg: str) -> None:
        raise LedgerError(f"{kind} on {t.date}: {msg}")

    if kind not in TYPE_ORDER:
        fail("unknown transaction type")
    if kind in _UNIT_TYPES and not has_inst:
        fail("instrument is required")
    if kind in {"BUY", "SELL"} and t.units <= 0:
        fail("units must be positive")
    if kind == "BUY" and t.amount_gbp > 0:
        fail("amount_gbp must be <= 0 (cash leaves the account)")
    if kind == "SELL" and t.amount_gbp < 0:
        fail("amount_gbp must be >= 0 (cash enters the account)")
    if kind in {"DEPOSIT", "DIVIDEND", "INTEREST"} and t.amount_gbp < 0:
        fail("amount_gbp must be >= 0")
    if kind in {"WITHDRAWAL", "FEE", "TAX"} and t.amount_gbp > 0:
        fail("amount_gbp must be <= 0")
    if kind == "SPLIT" and not (t.split_ratio and t.split_ratio > 0):
        fail("split_ratio must be positive")
    if kind in {"OPENING_BALANCE", "TRANSFER_IN", "TRANSFER_OUT"} and has_inst and t.units <= 0:
        fail("units must be positive")
    if kind in {"OPENING_BALANCE", "TRANSFER_IN"} and t.cost_basis_gbp < 0:
        fail("cost_basis_gbp must be >= 0")


def sort_key(t: Txn) -> tuple[date, int, int]:
    return (t.date, TYPE_ORDER.get(t.type, 99), t.id)


def _position(state: LedgerState, t: Txn) -> Position:
    assert t.instrument_id is not None
    return state.positions.setdefault(t.instrument_id, Position())


def _remove_units(state: LedgerState, t: Txn, strict: bool) -> tuple[Position, float, float]:
    """Take up to t.units out of a position at average cost. Returns (position, units, cost)."""
    pos = _position(state, t)
    units = t.units
    if units > pos.units + EPS_UNITS:
        msg = f"{t.date}: {t.type} {t.units:g} units of instrument {t.instrument_id}, held {pos.units:g}"
        if strict:
            raise LedgerError(msg)
        state.warnings.append(msg)
        units = pos.units
    cost = pos.avg_cost_gbp * units
    pos.units -= units
    pos.cost_gbp -= cost
    if pos.units <= EPS_UNITS:
        pos.units, pos.cost_gbp = 0.0, 0.0
    return pos, units, cost


def apply(state: LedgerState, t: Txn, strict: bool = False) -> None:
    """Apply one transaction to `state` in place."""
    validate_txn(t)
    kind, amount = t.type, t.amount_gbp

    if kind in {"BUY", "OPENING_BALANCE", "TRANSFER_IN", "ADJUSTMENT"} and t.instrument_id is not None:
        pos = _position(state, t)
        was_empty = pos.units <= EPS_UNITS
        if kind == "BUY":
            pos.units += t.units
            pos.cost_gbp += -amount
        else:
            pos.units += t.units
            pos.cost_gbp += t.cost_basis_gbp
        if pos.units < -EPS_UNITS:
            msg = f"{t.date}: ADJUSTMENT leaves instrument {t.instrument_id} with negative units"
            if strict:
                raise LedgerError(msg)
            state.warnings.append(msg)
        if pos.units <= EPS_UNITS:
            pos.units, pos.cost_gbp = 0.0, 0.0
        elif was_empty:
            pos.first_date = t.date
        state.cash_gbp += amount
        if kind == "TRANSFER_IN":
            state.net_contributions_gbp += amount + t.cost_basis_gbp
        return

    if kind == "SELL":
        pos, units, cost = _remove_units(state, t, strict)
        proceeds = amount * (units / t.units) if t.units else 0.0
        gain = proceeds - cost
        pos.realised_gain_gbp += gain
        state.realised_gain_gbp += gain
        state.cash_gbp += amount
        return

    if kind == "TRANSFER_OUT" and t.instrument_id is not None:
        _pos, _units, cost = _remove_units(state, t, strict)
        state.cash_gbp += amount
        state.net_contributions_gbp += amount - cost
        return

    if kind == "SPLIT":
        pos = _position(state, t)
        pos.units *= t.split_ratio or 1.0
        return

    # cash-only transactions
    state.cash_gbp += amount
    if kind in {"DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT"}:
        state.net_contributions_gbp += amount
    elif kind in {"DIVIDEND", "INTEREST"}:
        state.income_gbp += amount
    elif kind in {"FEE", "TAX"}:
        state.fees_gbp += -amount


def replay(txns: Iterable[Txn], as_of: date | None = None, strict: bool = False) -> LedgerState:
    """State after every transaction dated on or before `as_of` (all when None)."""
    state = LedgerState()
    for t in sorted(txns, key=sort_key):
        if as_of is not None and t.date > as_of:
            break
        apply(state, t, strict)
    return state


def replay_series(
    txns: Iterable[Txn], dates: Sequence[date], strict: bool = False
) -> list[LedgerState]:
    """State at the end of each date in ascending `dates`, in one pass."""
    ordered = sorted(txns, key=sort_key)
    state, out, i = LedgerState(), [], 0
    for d in dates:
        while i < len(ordered) and ordered[i].date <= d:
            apply(state, ordered[i], strict)
            i += 1
        out.append(state.copy())
    return out


def position_target_adjustment(
    state: LedgerState, instrument_id: int, target_units: float, target_avg_cost_gbp: float
) -> tuple[float, float]:
    """(units_delta, cost_delta) that moves a position to the user's typed units and average cost."""
    if target_units < 0 or target_avg_cost_gbp < 0:
        raise LedgerError("target units and average cost must be >= 0")
    pos = state.positions.get(instrument_id, Position())
    return target_units - pos.units, target_units * target_avg_cost_gbp - pos.cost_gbp


def cash_target_adjustment(state: LedgerState, target_cash_gbp: float) -> float:
    """Cash delta that moves the account's uninvested cash to the user's typed figure."""
    return target_cash_gbp - state.cash_gbp
