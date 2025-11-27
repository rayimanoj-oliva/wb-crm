"""
Create number_flow_configs table to manage per-number flow toggles

Revision ID: 20251127_add_number_flow_configs
Revises: e0e2f22020cf
Create Date: 2025-11-27 12:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
import datetime
import uuid

# revision identifiers, used by Alembic.
revision: str = "20251127_add_number_flow_configs"
down_revision: Union[str, None] = "e0e2f22020cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_exists = inspector.has_table("number_flow_configs")

    if not table_exists:
        op.create_table(
            "number_flow_configs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("phone_number_id", sa.String(), nullable=False),
            sa.Column("display_number", sa.String(), nullable=False),
            sa.Column("display_digits", sa.String(length=20), nullable=True),
            sa.Column("flow_key", sa.String(length=100), nullable=False),
            sa.Column("flow_name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("phone_number_id", name="uq_number_flow_configs_phone"),
            sa.UniqueConstraint("display_digits", name="uq_number_flow_configs_digits"),
        )
        existing_indexes = set()
    else:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("number_flow_configs")}

    phone_index_name = op.f("ix_number_flow_configs_phone_number_id")
    digits_index_name = op.f("ix_number_flow_configs_display_digits")

    if phone_index_name not in existing_indexes:
        op.create_index(
            phone_index_name,
            "number_flow_configs",
            ["phone_number_id"],
            unique=False,
        )

    if digits_index_name not in existing_indexes:
        op.create_index(
            digits_index_name,
            "number_flow_configs",
            ["display_digits"],
            unique=False,
        )

    now = datetime.datetime.utcnow()
    seed_rows = [
        {
            "id": uuid.uuid4(),
            "phone_number_id": "367633743092037",
            "display_number": "+91 77299 92376",
            "display_digits": "7729992376",
            "flow_key": "lead_appointment",
            "flow_name": "Lead Appointment Flow",
            "description": "Meta ads lead-to-appointment automation on the dedicated booking number.",
            "priority": 1,
            "is_enabled": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": uuid.uuid4(),
            "phone_number_id": "848542381673826",
            "display_number": "+91 82978 82978",
            "display_digits": "8297882978",
            "flow_key": "treatment_primary",
            "flow_name": "Treatment Flow - Primary Number",
            "description": "Primary marketing/treatment automation for inbound leads.",
            "priority": 2,
            "is_enabled": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": uuid.uuid4(),
            "phone_number_id": "859830643878412",
            "display_number": "+91 76176 13030",
            "display_digits": "7617613030",
            "flow_key": "treatment_secondary",
            "flow_name": "Treatment Flow - Secondary Number",
            "description": "Secondary treatment automation number used for marketing flows.",
            "priority": 3,
            "is_enabled": True,
            "created_at": now,
            "updated_at": now,
        },
    ]

    insert_stmt = text(
        """
        INSERT INTO number_flow_configs (
            id,
            phone_number_id,
            display_number,
            display_digits,
            flow_key,
            flow_name,
            description,
            priority,
            is_enabled,
            created_at,
            updated_at
        ) VALUES (
            :id,
            :phone_number_id,
            :display_number,
            :display_digits,
            :flow_key,
            :flow_name,
            :description,
            :priority,
            :is_enabled,
            :created_at,
            :updated_at
        )
        ON CONFLICT (phone_number_id) DO NOTHING
        """
    )

    for row in seed_rows:
        bind.execute(insert_stmt, row)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_number_flow_configs_display_digits")
    op.execute("DROP INDEX IF EXISTS ix_number_flow_configs_phone_number_id")
    op.drop_table("number_flow_configs")

