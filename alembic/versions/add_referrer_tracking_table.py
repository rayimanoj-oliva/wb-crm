"""Add referrer tracking table

Revision ID: add_referrer_tracking
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_referrer_tracking'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create referrer_tracking table
    op.create_table('referrer_tracking',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wa_id', sa.String(), nullable=True),
        sa.Column('utm_source', sa.String(), nullable=True),
        sa.Column('utm_medium', sa.String(), nullable=True),
        sa.Column('utm_campaign', sa.String(), nullable=True),
        sa.Column('utm_content', sa.String(), nullable=True),
        sa.Column('referrer_url', sa.String(), nullable=True),
        sa.Column('center_name', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_referrer_tracking_id'), 'referrer_tracking', ['id'], unique=False)
    op.create_index(op.f('ix_referrer_tracking_wa_id'), 'referrer_tracking', ['wa_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_referrer_tracking_wa_id'), table_name='referrer_tracking')
    op.drop_index(op.f('ix_referrer_tracking_id'), table_name='referrer_tracking')
    op.drop_table('referrer_tracking')