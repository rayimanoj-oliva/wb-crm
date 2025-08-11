"""Add template_status and failure_reason to messages

Revision ID: 1035aa95dabe
Revises: 065247aa21fd
Create Date: 2025-08-08 16:41:02.667262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1035aa95dabe'
down_revision: Union[str, None] = '065247aa21fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
