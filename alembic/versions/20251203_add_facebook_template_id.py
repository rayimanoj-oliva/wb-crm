"""
Add facebook_template_id, created_at, and updated_at columns to templates table

Revision ID: 20251203_add_facebook_template_id
Revises: 20251128_add_quick_replies
Create Date: 2025-12-03 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20251203_add_facebook_template_id"
down_revision: Union[str, None] = "20251128_add_quick_replies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("templates"):
        return

    columns = [col["name"] for col in inspector.get_columns("templates")]

    # Add facebook_template_id column if it doesn't exist
    if "facebook_template_id" not in columns:
        op.add_column(
            "templates",
            sa.Column("facebook_template_id", sa.String(), nullable=True)
        )
        op.create_index(
            "ix_templates_facebook_template_id",
            "templates",
            ["facebook_template_id"]
        )

    # Add created_at column if it doesn't exist
    if "created_at" not in columns:
        op.add_column(
            "templates",
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now())
        )

    # Add updated_at column if it doesn't exist
    if "updated_at" not in columns:
        op.add_column(
            "templates",
            sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now())
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("templates"):
        return

    columns = [col["name"] for col in inspector.get_columns("templates")]

    if "updated_at" in columns:
        op.drop_column("templates", "updated_at")

    if "created_at" in columns:
        op.drop_column("templates", "created_at")

    if "facebook_template_id" in columns:
        op.drop_index("ix_templates_facebook_template_id", table_name="templates")
        op.drop_column("templates", "facebook_template_id")
