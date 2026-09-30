"""imports

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-09-16 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: str | Sequence[str] | None = 'd3e4f5a6b7c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'import_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.Enum('transactions', 'balances', name='importkind'), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('profile_name', sa.String(), nullable=True),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('header_signature', sa.String(), nullable=True),
        sa.Column('mapping_json', sa.Text(), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.Column('rows_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rows_imported', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rows_skipped', sa.Integer(), server_default='0', nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'previewed', 'committed', 'rolled_back', name='importstatus'),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('row_errors_json', sa.Text(), nullable=True),
        sa.Column('earliest_date', sa.Date(), nullable=True),
        sa.Column('deleted_stand_ins_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'import_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('kind', sa.Enum('transactions', 'balances', name='importkind'), nullable=False),
        sa.Column('mapping_json', sa.Text(), nullable=False),
        sa.Column('header_signature', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_import_profiles_name'),
    )

    op.create_table(
        'instrument_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.String(), nullable=False),
        sa.Column('profile_name', sa.String(), nullable=True),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alias', 'profile_name', name='uq_instrument_aliases_alias_profile'),
    )

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('import_batch_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('external_id', sa.String(), nullable=True))
        batch_op.create_foreign_key(
            'fk_transactions_import_batch_id', 'import_batches', ['import_batch_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_transactions_account_external_id', ['account_id', 'external_id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index('ix_transactions_account_external_id')
        batch_op.drop_constraint('fk_transactions_import_batch_id', type_='foreignkey')
        batch_op.drop_column('external_id')
        batch_op.drop_column('import_batch_id')

    op.drop_table('instrument_aliases')
    op.drop_table('import_profiles')
    op.drop_table('import_batches')
