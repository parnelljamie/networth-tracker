from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_utc, today
from app.models.accounts import Account
from app.models.positions import Position
from app.schemas.holdings import HoldingPosition, Holdings, HoldingsTotals
from app.schemas.instrument import InstrumentOut
from app.services import price_service


def build_holdings(db: Session, account: Account) -> Holdings:
    positions = list(db.scalars(select(Position).where(Position.account_id == account.id)).all())
    on = today()

    priced = []
    total_value = 0.0
    total_cost = 0.0
    total_day_change = 0.0
    for pos in positions:
        result = price_service.price_gbp(db, pos.instrument, on, live=True)
        value = pos.units * result.price_gbp
        day_change = price_service.day_change_contribution(pos.instrument, pos.units, on, db)
        priced.append((pos, result, value, day_change))
        total_value += value
        total_cost += pos.cost_basis_gbp
        total_day_change += day_change

    rows: list[HoldingPosition] = []
    for pos, result, value, day_change in priced:
        gain = value - pos.cost_basis_gbp
        gain_pct = gain / pos.cost_basis_gbp if pos.cost_basis_gbp else None
        prev_value = value - day_change
        day_change_pct = day_change / prev_value if prev_value else None
        rows.append(
            HoldingPosition(
                instrument=InstrumentOut.model_validate(pos.instrument),
                units=pos.units,
                avg_cost_gbp=round(pos.cost_basis_gbp / pos.units, 4) if pos.units else 0.0,
                cost_basis_gbp=pos.cost_basis_gbp,
                price_gbp=result.price_gbp,
                price_at=pos.instrument.last_price_at,
                is_stale=result.is_stale,
                value_gbp=round(value, 2),
                gain_gbp=round(gain, 2),
                gain_pct=gain_pct,
                day_change_gbp=round(day_change, 2),
                day_change_pct=day_change_pct,
                weight=round(value / total_value, 4) if total_value else 0.0,
            )
        )

    total_gain = total_value - total_cost
    total_gain_pct = total_gain / total_cost if total_cost else None
    prev_total_value = total_value - total_day_change
    total_day_change_pct = total_day_change / prev_total_value if prev_total_value else None

    return Holdings(
        account_id=account.id,
        as_of=now_utc(),
        cash_gbp=account.cash_balance_gbp,
        positions=rows,
        totals=HoldingsTotals(
            value_gbp=round(total_value, 2),
            cost_basis_gbp=round(total_cost, 2),
            gain_gbp=round(total_gain, 2),
            gain_pct=total_gain_pct,
            day_change_gbp=round(total_day_change, 2),
            day_change_pct=total_day_change_pct,
        ),
        warnings=[],
    )
