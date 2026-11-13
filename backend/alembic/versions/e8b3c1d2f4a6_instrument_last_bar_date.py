"""instruments remember which trading day their latest quote is from

Revision ID: e8b3c1d2f4a6
Revises: d5a2b8c4e6f1
Create Date: 2026-11-13 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8b3c1d2f4a6'
down_revision: str | Sequence[str] | None = 'd5a2b8c4e6f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_bar_date', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('instruments', schema=None) as batch_op:
        batch_op.drop_column('last_bar_date')
