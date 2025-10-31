"""remove unused follow_up columns from customers

Revision ID: 5ac4e73c19d6
Revises: d7669e22858c
Create Date: 2025-10-31 16:17:28.234537

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ac4e73c19d6'
down_revision: Union[str, None] = 'd7669e22858c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
