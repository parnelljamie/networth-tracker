"""recurring plans and allocations

Revision ID: 7a1c2d3e4f50
Revises: 0b497fbd3481
Create Date: 2026-09-16 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7a1c2d3e4f50'
down_revision: str | Sequence[str] | None = '0b497fbd3481'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'recurring_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('kind', sa.Enum('contribution', 'withdrawal', 'overpayment', name='plankind'), nullable=False),
        sa.Column('amount_gbp', sa.Float(), nullable=False),
        sa.Column(
            'frequency',
            sa.Enum('weekly', 'fortnightly', 'monthly', 'quarterly', 'annually', name='frequency'),
            nullable=False,
        ),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('annual_increase_rate', sa.Float(), server_default='0', nullable=False),
        sa.Column(
            'contribution_source',
            sa.Enum(
                'personal', 'employer', 'salary_sacrifice', 'tax_relief', 'government_bonus', 'transfer',
                name='contributionsource',
            ),
            server_default='personal',
            nullable=False,
        ),
        sa.Column('tax_relief_rate', sa.Float(), server_default='0', nullable=False),
        sa.Column('auto_record', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('last_recorded_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'recurring_plan_allocations',
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['recurring_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ),
        sa.PrimaryKeyConstraint('plan_id', 'instrument_id'),
    )
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recurring_plan_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_transactions_recurring_plan_id', 'recurring_plans', ['recurring_plan_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_recurring_plan_id', type_='foreignkey')
        batch_op.drop_column('recurring_plan_id')
    op.drop_table('recurring_plan_allocations')
    op.drop_table('recurring_plans')
