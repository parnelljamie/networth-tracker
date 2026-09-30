"""sync tables (docs/07-mobile.md: paired phones, applied ops, phone outbox)

Revision ID: a11a6a3defe3
Revises: a9d8e7f6c5b4
Create Date: 2026-09-22 19:05:40.206300

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a11a6a3defe3'
down_revision: str | Sequence[str] | None = 'a9d8e7f6c5b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sync_devices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('paired_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=True),
    sa.Column('last_sync_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_table('sync_outbox',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('op_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('method', sa.String(), nullable=False),
    sa.Column('path', sa.String(), nullable=False),
    sa.Column('query', sa.String(), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('response', sa.Text(), nullable=True),
    sa.Column('summary', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('op_id')
    )
    op.create_table('sync_applied_ops',
    sa.Column('op_id', sa.String(), nullable=False),
    sa.Column('device_id', sa.Integer(), nullable=False),
    sa.Column('applied_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('id_map', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['sync_devices.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('op_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sync_applied_ops')
    op.drop_table('sync_outbox')
    op.drop_table('sync_devices')
