"""
Create quick replies table for reusable chat responses

Revision ID: 20251128_add_quick_replies
Revises: 20251127_add_flow_sched
Create Date: 2025-11-28 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20251128_add_quick_replies"
down_revision: Union[str, None] = "20251127_add_flow_sched"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("quick_replies"):
        return

    op.create_table(
        "quick_replies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_quick_replies_created_by_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quick_replies_category"), "quick_replies", ["category"], unique=False)
    op.create_index(op.f("ix_quick_replies_created_at"), "quick_replies", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quick_replies_created_at"), table_name="quick_replies")
    op.drop_index(op.f("ix_quick_replies_category"), table_name="quick_replies")
    op.drop_table("quick_replies")


