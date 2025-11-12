"""Add response_json column to flow_logs

Revision ID: 1f3d8d21c6ab
Revises: 981458db74d2
Create Date: 2025-11-12 11:45:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f3d8d21c6ab"
down_revision: Union[str, None] = "981458db74d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("flow_logs", sa.Column("response_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("flow_logs", "response_json")
