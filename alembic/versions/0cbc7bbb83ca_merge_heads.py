"""merge heads

Revision ID: 0cbc7bbb83ca
Revises: df2591058689, 20251028_add_phone_columns
Create Date: 2025-10-28 20:45:32.836347

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cbc7bbb83ca'
down_revision: Union[str, None] = ('df2591058689', '20251028_add_phone_columns')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
