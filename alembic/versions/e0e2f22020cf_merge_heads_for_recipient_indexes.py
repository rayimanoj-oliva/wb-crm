"""merge heads for recipient indexes

Revision ID: e0e2f22020cf
Revises: 1f3d8d21c6ab
Create Date: 2025-11-26 18:13:31.934318

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0e2f22020cf'
down_revision: Union[str, None] = '1f3d8d21c6ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
