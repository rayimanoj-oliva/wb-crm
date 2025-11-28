"""
Add WhatsApp API debug log table

Revision ID: 20251128_add_wa_api_log
Revises: 20251128_fix_cascade_deletes
Create Date: 2025-11-28
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "20251128_add_wa_api_log"
down_revision: Union[str, None] = "20251128_fix_cascade_deletes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'whatsapp_api_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('campaign_id', UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('job_id', UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('phone_number', sa.String(20), nullable=True, index=True),

        # Request details
        sa.Column('request_url', sa.String(500), nullable=True),
        sa.Column('request_payload', JSONB, nullable=True),
        sa.Column('request_headers', JSONB, nullable=True),

        # Response details
        sa.Column('response_status_code', sa.Integer, nullable=True),
        sa.Column('response_body', JSONB, nullable=True),
        sa.Column('response_headers', JSONB, nullable=True),

        # Meta message details
        sa.Column('whatsapp_message_id', sa.String(100), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),

        # Timing
        sa.Column('request_time', sa.DateTime, nullable=True),
        sa.Column('response_time', sa.DateTime, nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True),

        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), index=True),
    )

    # Index for quick lookups
    op.create_index('ix_wa_api_logs_phone_created', 'whatsapp_api_logs', ['phone_number', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_wa_api_logs_phone_created')
    op.drop_table('whatsapp_api_logs')
