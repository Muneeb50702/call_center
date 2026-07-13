"""Add call transcript, direction, sentiment, exception_peak columns

Revision ID: c1a2b3c4d5e6
Revises: b73d31748668
Create Date: 2026-07-11

Adds Phase 0 columns to the ``calls`` table so live transcripts, call
direction, sentiment and the peak supervisor-attention score are persisted
(in dev these are also created by init_db()/create_all; this migration keeps
prod in sync).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'b73d31748668'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'calls',
        sa.Column('direction', sa.String(length=16), nullable=False, server_default='inbound'),
    )
    op.add_column('calls', sa.Column('transcript', sa.JSON(), nullable=True))
    op.add_column(
        'calls',
        sa.Column('sentiment', sa.String(length=16), nullable=False, server_default='neutral'),
    )
    op.add_column(
        'calls',
        sa.Column('exception_peak', sa.Float(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('calls', 'exception_peak')
    op.drop_column('calls', 'sentiment')
    op.drop_column('calls', 'transcript')
    op.drop_column('calls', 'direction')
