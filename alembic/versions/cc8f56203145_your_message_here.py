"""your message here

Revision ID: cc8f56203145
Revises: f76dcc5af7fc
Create Date: 2025-06-24 11:51:51.471521

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc8f56203145'
down_revision: Union[str, None] = 'f76dcc5af7fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
