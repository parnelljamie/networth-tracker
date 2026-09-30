"""account snapshots

Revision ID: a1b2c3d4e5f6
Revises: 9590ae349902
Create Date: 2026-09-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '9590ae349902'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('account_snapshots',
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('value_gbp', sa.Float(), nullable=False),
    sa.Column('cost_basis_gbp', sa.Float(), nullable=True),
    sa.Column('net_contributions_gbp', sa.Float(), nullable=True),
    sa.Column('is_estimated', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('source', sa.Enum('daily', 'backfill', 'rebuild', name='snapshotsource'), server_default='daily', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id', 'date')
    )
    with op.batch_alter_table('account_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_account_snapshots_date', ['date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('account_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_account_snapshots_date')

    op.drop_table('account_snapshots')
