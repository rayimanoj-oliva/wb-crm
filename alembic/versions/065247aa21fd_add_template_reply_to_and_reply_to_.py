"""Add template_reply_to and reply_to_message_id to Message

Revision ID: 065247aa21fd
Revises: cf0db4353355
Create Date: 2025-08-08 16:21:11.297844
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '065247aa21fd'
down_revision: Union[str, None] = 'cf0db4353355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add only the columns you want, as simple strings
    op.add_column('messages', sa.Column('template_reply_to', sa.String(), nullable=True))
    op.add_column('messages', sa.Column('reply_to_message_id', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop only the columns you added
    op.drop_column('messages', 'reply_to_message_id')
    op.drop_column('messages', 'template_reply_to')
