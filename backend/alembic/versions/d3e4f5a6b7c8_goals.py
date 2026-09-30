"""goals

Revision ID: d3e4f5a6b7c8
Revises: b2c3d4e5f601
Create Date: 2026-09-16 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: str | Sequence[str] | None = 'b2c3d4e5f601'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('target_gbp', sa.Float(), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column(
            'scope',
            sa.Enum('household', 'person', 'account', 'category', name='goalscope'),
            nullable=False,
        ),
        sa.Column('person_id', sa.Integer(), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column(
            'category',
            sa.Enum(
                'investment', 'pension', 'cash', 'property', 'mortgage', 'loan', 'credit_card',
                'other_asset', 'other_liability', name='category',
            ),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('goals')
