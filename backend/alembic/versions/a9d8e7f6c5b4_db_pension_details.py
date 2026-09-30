"""db pension details

Revision ID: a9d8e7f6c5b4
Revises: f7c1d2e3a4b5
Create Date: 2026-09-18 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a9d8e7f6c5b4'
down_revision: str | Sequence[str] | None = 'f7c1d2e3a4b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_METHODS = ('holdings', 'balance', 'model', 'amortising')
NEW_METHODS = (*OLD_METHODS, 'defined_benefit')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('db_pension_details',
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('scheme', sa.String(), server_default='tps_2015', nullable=False),
    sa.Column('accrued_annual_pension_gbp', sa.Float(), nullable=False),
    sa.Column('accrued_lump_sum_gbp', sa.Float(), server_default='0', nullable=False),
    sa.Column('accrued_as_of', sa.Date(), nullable=False),
    sa.Column('accrual_rate', sa.Float(), nullable=False),
    sa.Column('revaluation_above_cpi', sa.Float(), server_default='0', nullable=False),
    sa.Column('pensionable_salary_gbp', sa.Float(), server_default='0', nullable=False),
    sa.Column('salary_growth_rate', sa.Float(), server_default='0', nullable=False),
    sa.Column('normal_pension_age', sa.Integer(), nullable=False),
    sa.Column('is_active_member', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('capitalisation_factor', sa.Float(), server_default='20', nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id')
    )
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.alter_column(
            'valuation_method',
            existing_type=sa.Enum(*OLD_METHODS, name='valuationmethod'),
            type_=sa.Enum(*NEW_METHODS, name='valuationmethod'),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.alter_column(
            'valuation_method',
            existing_type=sa.Enum(*NEW_METHODS, name='valuationmethod'),
            type_=sa.Enum(*OLD_METHODS, name='valuationmethod'),
            existing_nullable=False,
        )
    op.drop_table('db_pension_details')
