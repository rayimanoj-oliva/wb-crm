"""added some changes to campaign model

Revision ID: 099538a46dd9
Revises: cc8f56203145
Create Date: 2025-06-24 16:35:32.542710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '099538a46dd9'
down_revision: Union[str, None] = 'cc8f56203145'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
