"""manual instruments can follow a Yahoo instrument's price

Revision ID: c3f1a9e2b7d4
Revises: b7e2c4d1f9a3
Create Date: 2026-09-28 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f1a9e2b7d4'
down_revision: str | Sequence[str] | None = 'b7e2c4d1f9a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tracks_instrument_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_instruments_tracks_instrument_id', 'instruments', ['tracks_instrument_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_instruments_tracks_instrument_id', type_='foreignkey')
        batch_op.drop_column('tracks_instrument_id')
