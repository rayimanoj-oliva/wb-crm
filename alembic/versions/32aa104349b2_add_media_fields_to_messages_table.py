"""Add media fields to messages table

Revision ID: 32aa104349b2
Revises: 62d83359a6f2
Create Date: 2025-06-18 15:48:11.536915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32aa104349b2'
down_revision: Union[str, None] = '62d83359a6f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
