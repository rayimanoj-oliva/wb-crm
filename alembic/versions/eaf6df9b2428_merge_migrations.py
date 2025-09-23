"""merge migrations

Revision ID: eaf6df9b2428
Revises: 1a2b3c4d5e6f, fccced65b167
Create Date: 2025-09-23 11:39:17.731133

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eaf6df9b2428'
down_revision: Union[str, None] = ('1a2b3c4d5e6f', 'fccced65b167')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
