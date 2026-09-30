"""baseline

Revision ID: 38f2e12bc200
Revises: 
Create Date: 2026-09-15 20:47:20.600062

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '38f2e12bc200'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
