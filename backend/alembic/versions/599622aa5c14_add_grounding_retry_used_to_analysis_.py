"""add grounding_retry_used to analysis_results

Revision ID: 599622aa5c14
Revises: 6224f8f082fb
Create Date: 2026-08-26 15:43:08.135031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '599622aa5c14'
down_revision: Union[str, Sequence[str], None] = '6224f8f082fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default is required here (unlike the ORM-level Python default
    # alone) so this NOT NULL column can be added to a table that may
    # already have rows on a real Postgres database, not just a fresh one.
    op.add_column(
        'analysis_results',
        sa.Column('grounding_retry_used', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('analysis_results', 'grounding_retry_used')
