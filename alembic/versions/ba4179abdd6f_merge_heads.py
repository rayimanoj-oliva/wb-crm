"""merge heads

Revision ID: ba4179abdd6f
Revises: add_referrer_tracking, eaf6df9b2428
Create Date: 2025-09-27 16:01:26.520154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba4179abdd6f'
down_revision: Union[str, None] = ('add_referrer_tracking', 'eaf6df9b2428')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
