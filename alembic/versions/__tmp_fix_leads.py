"""add_leads_table

Revision ID: add_leads_manual
Revises: 75c80dc2ffd4
Create Date: 2025-10-28 11:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_leads_manual'
down_revision: Union[str, None] = '75c80dc2ffd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create leads table."""
    op.create_table('leads',
    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('zoho_lead_id', sa.String(), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=False),
    sa.Column('last_name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('mobile', sa.String(length=20), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=True),
    sa.Column('lead_source', sa.String(length=100), nullable=True),
    sa.Column('lead_status', sa.String(length=50), nullable=True),
    sa.Column('company', sa.String(length=100), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('wa_id', sa.String(), nullable=False),
    sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('appointment_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('treatment_name', sa.String(length=255), nullable=True),
    sa.Column('zoho_mapped_concern', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_leads_zoho_lead_id', 'leads', ['zoho_lead_id'], unique=True)
    op.create_index('ix_leads_wa_id', 'leads', ['wa_id'], unique=False)
    op.create_index('ix_leads_phone', 'leads', ['phone'], unique=False)


def downgrade() -> None:
    """Drop leads table."""
    op.drop_index('ix_leads_phone', table_name='leads')
    op.drop_index('ix_leads_wa_id', table_name='leads')
    op.drop_index('ix_leads_zoho_lead_id', table_name='leads')
    op.drop_table('leads')

