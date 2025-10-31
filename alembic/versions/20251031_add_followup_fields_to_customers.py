"""add follow-up tracking fields to customers

Revision ID: 20251031_add_followup_fields
Revises: 20251028_add_phone_columns
Create Date: 2025-10-31 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '20251031_add_followup_fields'
down_revision: Union[str, None] = '20251028_add_phone_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add follow-up fields to customers."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("customers")]

    with op.batch_alter_table("customers") as batch_op:
        if "last_interaction_time" not in existing_columns:
            batch_op.add_column(sa.Column("last_interaction_time", sa.DateTime(), nullable=True))
        if "last_message_type" not in existing_columns:
            batch_op.add_column(sa.Column("last_message_type", sa.String(length=50), nullable=True))
        if "next_followup_time" not in existing_columns:
            batch_op.add_column(sa.Column("next_followup_time", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema: drop follow-up fields from customers."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("customers")]

    with op.batch_alter_table("customers") as batch_op:
        if "next_followup_time" in existing_columns:
            batch_op.drop_column("next_followup_time")
        if "last_message_type" in existing_columns:
            batch_op.drop_column("last_message_type")
        if "last_interaction_time" in existing_columns:
            batch_op.drop_column("last_interaction_time")
