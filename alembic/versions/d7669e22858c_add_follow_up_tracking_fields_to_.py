"""add follow-up tracking fields to customers

Revision ID: d7669e22858c
Revises: 0cbc7bbb83ca
Create Date: 2025-10-31 15:16:23.837665
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7669e22858c'
down_revision: Union[str, None] = '0cbc7bbb83ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ✅ Only keep the fields actually needed for follow-up tracking
    op.add_column('customers', sa.Column('last_interaction_time', sa.DateTime(), nullable=True))
    op.add_column('customers', sa.Column('last_message_type', sa.String(length=50), nullable=True))
    op.add_column('customers', sa.Column('next_followup_time', sa.DateTime(), nullable=True))
    # ❌ Removed follow_up_step and follow_up_status


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('customers', 'next_followup_time')
    op.drop_column('customers', 'last_message_type')
    op.drop_column('customers', 'last_interaction_time')
