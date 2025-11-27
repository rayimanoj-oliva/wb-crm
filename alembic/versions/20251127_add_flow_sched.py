"""
Add auto-enable scheduling columns to number_flow_configs

Revision ID: 20251127_add_flow_sched
Revises: 20251127_add_number_flow_configs
Create Date: 2025-11-27 19:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20251127_add_flow_sched"
down_revision: Union[str, None] = "20251127_add_number_flow_configs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("number_flow_configs"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("number_flow_configs")}

    if "auto_enable_from" not in existing_columns:
        op.add_column("number_flow_configs", sa.Column("auto_enable_from", sa.DateTime(), nullable=True))

    if "auto_enable_to" not in existing_columns:
        op.add_column("number_flow_configs", sa.Column("auto_enable_to", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("number_flow_configs"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("number_flow_configs")}

    if "auto_enable_to" in existing_columns:
        op.drop_column("number_flow_configs", "auto_enable_to")

    if "auto_enable_from" in existing_columns:
        op.drop_column("number_flow_configs", "auto_enable_from")


