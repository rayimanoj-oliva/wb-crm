"""Add whatsapp_numbers table and organization_id to customers

Revision ID: add_whatsapp_numbers
Revises: add_code_to_orgs
Create Date: 2024-12-29 14:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'add_whatsapp_numbers'
down_revision: Union[str, None] = 'add_code_to_orgs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # Check if whatsapp_numbers table already exists
    existing_tables = inspector.get_table_names()
    if 'whatsapp_numbers' not in existing_tables:
        # Create whatsapp_numbers table
        op.create_table(
            'whatsapp_numbers',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('phone_number_id', sa.String(length=100), nullable=False),
            sa.Column('display_number', sa.String(length=50), nullable=True),
            sa.Column('access_token', sa.String(length=500), nullable=True),
            sa.Column('webhook_path', sa.String(length=255), nullable=True),
            sa.Column('organization_id', UUID(as_uuid=True), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Create indexes
        op.create_index('ix_whatsapp_numbers_phone_number_id', 'whatsapp_numbers', ['phone_number_id'], unique=True)
        op.create_index('ix_whatsapp_numbers_organization_id', 'whatsapp_numbers', ['organization_id'])
    else:
        # Table exists, check if indexes exist
        try:
            whatsapp_num_indexes = [idx['name'] for idx in inspector.get_indexes('whatsapp_numbers')]
            if 'ix_whatsapp_numbers_phone_number_id' not in whatsapp_num_indexes:
                op.create_index('ix_whatsapp_numbers_phone_number_id', 'whatsapp_numbers', ['phone_number_id'], unique=True)
            if 'ix_whatsapp_numbers_organization_id' not in whatsapp_num_indexes:
                op.create_index('ix_whatsapp_numbers_organization_id', 'whatsapp_numbers', ['organization_id'])
        except Exception:
            pass  # Indexes might already exist
    
    # Check if organization_id column already exists in customers table
    customers_columns = [col["name"] for col in inspector.get_columns("customers")]
    
    if 'organization_id' not in customers_columns:
        # Add organization_id to customers table
        op.add_column('customers', sa.Column('organization_id', UUID(as_uuid=True), nullable=True))
        # Refresh columns list after adding
        customers_columns = [col["name"] for col in inspector.get_columns("customers")]
    
    # Only create index and FK if organization_id column exists
    if 'organization_id' in customers_columns:
        # Check if index exists before creating
        try:
            existing_indexes = [idx['name'] for idx in inspector.get_indexes('customers')]
            if 'ix_customers_organization_id' not in existing_indexes:
                op.create_index('ix_customers_organization_id', 'customers', ['organization_id'])
        except Exception:
            pass  # Index might already exist or inspector might fail
        
        # Check if foreign key exists before creating
        try:
            existing_fks = [fk.get('name') for fk in inspector.get_foreign_keys('customers')]
            if 'fk_customers_organization_id' not in existing_fks:
                op.create_foreign_key('fk_customers_organization_id', 'customers', 'organizations', ['organization_id'], ['id'])
        except Exception:
            pass  # FK might already exist or inspector might fail


def downgrade() -> None:
    # Drop organization_id from customers
    op.drop_constraint('fk_customers_organization_id', 'customers', type_='foreignkey')
    op.drop_index('ix_customers_organization_id', table_name='customers')
    op.drop_column('customers', 'organization_id')
    
    # Drop whatsapp_numbers table
    op.drop_index('ix_whatsapp_numbers_organization_id', table_name='whatsapp_numbers')
    op.drop_index('ix_whatsapp_numbers_phone_number_id', table_name='whatsapp_numbers')
    op.drop_table('whatsapp_numbers')

