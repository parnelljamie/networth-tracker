"""scenarios and scenario events

Revision ID: b2c3d4e5f601
Revises: 7a1c2d3e4f50
Create Date: 2026-09-16 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f601'
down_revision: str | Sequence[str] | None = '7a1c2d3e4f50'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('return_adjustment', sa.Float(), server_default='0', nullable=False),
        sa.Column('inflation_rate', sa.Float(), nullable=True),
        sa.Column('property_growth_rate', sa.Float(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'scenario_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('lump_sum', 'stop_plan', 'change_plan_amount', 'set_return_rate', name='scenarioeventkind'),
            nullable=False,
        ),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('amount_gbp', sa.Float(), nullable=True),
        sa.Column('rate', sa.Float(), nullable=True),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['plan_id'], ['recurring_plans.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    scenarios = sa.table(
        'scenarios',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('is_default', sa.Boolean),
        sa.column('return_adjustment', sa.Float),
    )
    op.bulk_insert(
        scenarios,
        [
            {'id': 1, 'name': 'Base', 'is_default': True, 'return_adjustment': 0.0},
            {'id': 2, 'name': 'Optimistic', 'is_default': False, 'return_adjustment': 0.02},
            {'id': 3, 'name': 'Pessimistic', 'is_default': False, 'return_adjustment': -0.02},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('scenario_events')
    op.drop_table('scenarios')
