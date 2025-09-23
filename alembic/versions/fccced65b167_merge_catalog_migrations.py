"""merge catalog migrations

Revision ID: fccced65b167
Revises: 317c1b381369, add_catalog_columns_20250922
Create Date: 2025-09-22 23:10:47.839063

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fccced65b167'
down_revision: Union[str, None] = ('317c1b381369', 'add_catalog_columns_20250922')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
