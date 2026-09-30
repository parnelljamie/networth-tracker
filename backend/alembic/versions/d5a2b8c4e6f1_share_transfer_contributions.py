"""recount saved net contributions now share transfers count at cost

Revision ID: d5a2b8c4e6f1
Revises: c3f1a9e2b7d4
Create Date: 2026-09-28 20:30:00.000000

Data only. The ledger now moves net contributions with shares transferred in or out (at cost),
so every saved snapshot of an account with such a transfer is recounted from its transactions.
Values and cost basis are unaffected, so nothing else needs rebuilding.
"""
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa

from alembic import op
from app.engine import ledger

# revision identifiers, used by Alembic.
revision: str = 'd5a2b8c4e6f1'
down_revision: str | Sequence[str] | None = 'c3f1a9e2b7d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def upgrade() -> None:
    conn = op.get_bind()
    account_ids = conn.execute(sa.text(
        "SELECT DISTINCT account_id FROM transactions WHERE status = 'confirmed' "
        "AND type IN ('TRANSFER_IN', 'TRANSFER_OUT') AND instrument_id IS NOT NULL"
    )).scalars().all()
    for account_id in account_ids:
        rows = conn.execute(sa.text(
            "SELECT id, date, type, instrument_id, units, amount_gbp, cost_basis_gbp, split_ratio "
            "FROM transactions WHERE account_id = :a AND status = 'confirmed'"
        ), {"a": account_id}).all()
        txns = [
            ledger.Txn(date=_day(r.date), type=r.type, instrument_id=r.instrument_id, units=r.units or 0.0,
                       amount_gbp=r.amount_gbp or 0.0, cost_basis_gbp=r.cost_basis_gbp or 0.0,
                       split_ratio=r.split_ratio, id=r.id)
            for r in rows
        ]
        dates = sorted(_day(d) for d in conn.execute(sa.text(
            "SELECT date FROM account_snapshots WHERE account_id = :a AND net_contributions_gbp IS NOT NULL"
        ), {"a": account_id}).scalars().all())
        if not dates:
            continue
        for on, state in zip(dates, ledger.replay_series(txns, dates), strict=True):
            conn.execute(sa.text(
                "UPDATE account_snapshots SET net_contributions_gbp = :n WHERE account_id = :a AND date = :d"
            ), {"n": round(state.net_contributions_gbp, 2), "a": account_id, "d": on.isoformat()})


def downgrade() -> None:
    pass
