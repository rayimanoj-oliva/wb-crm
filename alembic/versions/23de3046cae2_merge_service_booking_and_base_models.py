"""Merge service_booking and base models

Revision ID: 23de3046cae2
Revises: c04549456a9b, da2808dbdddb
Create Date: 2025-07-09 21:44:52.301149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23de3046cae2'
down_revision: Union[str, None] = ('c04549456a9b', 'da2808dbdddb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
