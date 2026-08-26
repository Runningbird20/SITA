"""add analysis_feedback table

Revision ID: 343eeedf2a94
Revises: 599622aa5c14
Create Date: 2026-08-26 15:52:15.060527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '343eeedf2a94'
down_revision: Union[str, Sequence[str], None] = '599622aa5c14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'analysis_feedback',
        sa.Column('analysis_result_id', sa.Uuid(), nullable=False),
        sa.Column('rating', sa.String(length=10), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['analysis_result_id'], ['analysis_results.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # unique=True enforces one feedback row per AnalysisResult at the DB level.
    op.create_index(
        op.f('ix_analysis_feedback_analysis_result_id'),
        'analysis_feedback',
        ['analysis_result_id'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_analysis_feedback_analysis_result_id'), table_name='analysis_feedback')
    op.drop_table('analysis_feedback')
