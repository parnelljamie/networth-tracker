"""broker links (Trading 212 API sync)

Revision ID: b7e2c4d1f9a3
Revises: a11a6a3defe3
Create Date: 2026-09-24 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e2c4d1f9a3'
down_revision: str | Sequence[str] | None = 'a11a6a3defe3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('broker_links',
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(), nullable=False),
    sa.Column('environment', sa.String(), nullable=False),
    sa.Column('key_hint', sa.String(), nullable=False),
    sa.Column('auto_sync', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('status', sa.String(), server_default='idle', nullable=False),
    sa.Column('status_message', sa.String(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('last_new_rows', sa.Integer(), server_default='0', nullable=False),
    sa.Column('pending_batch_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['pending_batch_id'], ['import_batches.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('account_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('broker_links')
