"""FK ondelete rules so any account/plan can be deleted

Deleting an account is now unrestricted (the "has balance history" guard is gone), so every FK
pointing at `accounts.id` / `recurring_plans.id` needs an explicit rule or the delete raises an
IntegrityError and surfaces as an HTTP 500:

* `loan_details.secured_on_account_id` -> SET NULL. Deleting the property a mortgage is secured
  on must keep the mortgage; it just becomes unlinked.
* `scenario_events.account_id`         -> CASCADE. The event is meaningless without its account.
* `scenario_events.plan_id`            -> CASCADE. Ditto for its recurring plan.
* `transactions.recurring_plan_id`     -> SET NULL. Recorded history outlives the plan that
  generated it (and deleting an account now cascades to its plans).

SQLite cannot alter a constraint in place, so each table is recreated via batch mode. The
existing constraints are unnamed, which means reflection cannot give alembic a name to drop; we
therefore hand batch mode a `copy_from` Table reflected from the live database and swap the
constraint on that object. Reflecting rather than hard-coding the column list keeps this correct
against a real database with drift, and batch mode copies all existing rows across.

Revision ID: f7c1d2e3a4b5
Revises: e5f6a7b8c9d0
Create Date: 2026-09-17 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7c1d2e3a4b5'
down_revision: str | Sequence[str] | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, constraint name, ondelete to apply on upgrade)
_CHANGES = [
    ('loan_details', 'secured_on_account_id', 'fk_loan_details_secured_on_account_id', 'SET NULL'),
    ('scenario_events', 'account_id', 'fk_scenario_events_account_id', 'CASCADE'),
    ('scenario_events', 'plan_id', 'fk_scenario_events_plan_id', 'CASCADE'),
    ('transactions', 'recurring_plan_id', 'fk_transactions_recurring_plan_id', 'SET NULL'),
]


def _set_ondelete(table_name: str, changes: list[tuple[str, str | None, str | None]]) -> None:
    """Recreate `table_name` with the given columns' FK ondelete rules replaced.

    `changes` is a list of (column, constraint_name, ondelete). `ondelete=None` removes the rule.
    """
    meta = sa.MetaData()
    table = sa.Table(table_name, meta, autoload_with=op.get_bind())

    for column, name, ondelete in changes:
        existing = next(
            fk
            for fk in table.constraints
            if isinstance(fk, sa.ForeignKeyConstraint)
            and [c.name for c in fk.columns] == [column]
        )
        target = list(existing.elements)[0].target_fullname
        # Detach the old constraint from both the table and the column, otherwise SQLAlchemy
        # renders it again alongside the replacement when batch mode recreates the table.
        table.constraints.discard(existing)
        for element in list(existing.elements):
            table.c[column].foreign_keys.discard(element)
        table.append_constraint(
            sa.ForeignKeyConstraint([column], [target], name=name, ondelete=ondelete)
        )

    with op.batch_alter_table(table_name, copy_from=table, recreate='always'):
        pass


def upgrade() -> None:
    """Upgrade schema."""
    for table_name in dict.fromkeys(t for t, _c, _n, _o in _CHANGES):
        _set_ondelete(
            table_name,
            [(c, n, o) for t, c, n, o in _CHANGES if t == table_name],
        )


def downgrade() -> None:
    """Downgrade schema.

    Recreates the same tables with the ondelete rules removed, i.e. back to plain unnamed-style
    foreign keys with no referential action. Row data is copied across unchanged; the only loss is
    the referential behaviour itself, so deleting an account referenced by these columns will
    once again raise an IntegrityError.
    """
    for table_name in dict.fromkeys(t for t, _c, _n, _o in _CHANGES):
        _set_ondelete(
            table_name,
            # name=None restores the original unnamed constraint shape exactly.
            [(c, None, None) for t, c, _n, _o in _CHANGES if t == table_name],
        )
