"""Add organizations and roles tables

Revision ID: add_orgs_roles_2024
Revises: 20251203_merge_heads
Create Date: 2024-12-19 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision: str = 'add_orgs_roles_2024'
down_revision: Union[str, None] = '20251203_merge_heads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Create roles table if it doesn't exist
    if 'roles' not in existing_tables:
        op.create_table('roles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
        op.create_index('ix_roles_name', 'roles', ['name'], unique=True)
    
    # Create organizations table if it doesn't exist
    if 'organizations' not in existing_tables:
        op.create_table('organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
        op.create_index('ix_organizations_name', 'organizations', ['name'], unique=False)
        op.create_index('ix_organizations_slug', 'organizations', ['slug'], unique=True)
    
    # Insert default roles if they don't exist
    op.execute("""
        INSERT INTO roles (id, name, display_name, description, is_active, created_at, updated_at)
        SELECT 
            gen_random_uuid(), 'SUPER_ADMIN', 'Super Admin', 'Full system access, can manage all organizations', true, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'SUPER_ADMIN');
        
        INSERT INTO roles (id, name, display_name, description, is_active, created_at, updated_at)
        SELECT 
            gen_random_uuid(), 'ORG_ADMIN', 'Organization Admin', 'Full access within their organization', true, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'ORG_ADMIN');
        
        INSERT INTO roles (id, name, display_name, description, is_active, created_at, updated_at)
        SELECT 
            gen_random_uuid(), 'AGENT', 'Agent', 'Standard user access within their organization', true, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'AGENT');
    """)
    
    # Add organization_id and role_id to users table (check if columns exist first)
    users_columns = [col["name"] for col in inspector.get_columns("users")]
    
    if 'organization_id' not in users_columns:
        op.add_column('users', sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    if 'role_id' not in users_columns:
        op.add_column('users', sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=True))
    if 'created_at' not in users_columns:
        op.add_column('users', sa.Column('created_at', sa.DateTime(), nullable=True))
    if 'updated_at' not in users_columns:
        op.add_column('users', sa.Column('updated_at', sa.DateTime(), nullable=True))
    
    # Refresh users_columns after potentially adding new columns
    users_columns = [col["name"] for col in inspector.get_columns("users")]
    
    # Create foreign keys (check if they exist first)
    fk_constraints = [fk['name'] for fk in inspector.get_foreign_keys('users')]
    if 'fk_users_organization_id' not in fk_constraints and 'organization_id' in users_columns:
        try:
            op.create_foreign_key('fk_users_organization_id', 'users', 'organizations', ['organization_id'], ['id'], ondelete='SET NULL')
        except:
            pass  # FK might already exist
    if 'fk_users_role_id' not in fk_constraints and 'role_id' in users_columns:
        try:
            op.create_foreign_key('fk_users_role_id', 'users', 'roles', ['role_id'], ['id'], ondelete='SET NULL')
        except:
            pass  # FK might already exist
    
    # Create indexes (check if they exist first)
    users_indexes = [idx['name'] for idx in inspector.get_indexes('users')]
    if 'ix_users_organization_id' not in users_indexes and 'organization_id' in users_columns:
        try:
            op.create_index('ix_users_organization_id', 'users', ['organization_id'], unique=False)
        except:
            pass
    if 'ix_users_role_id' not in users_indexes and 'role_id' in users_columns:
        try:
            op.create_index('ix_users_role_id', 'users', ['role_id'], unique=False)
        except:
            pass
    
    # Set default role_id for existing users (AGENT role)
    op.execute("""
        UPDATE users 
        SET role_id = (SELECT id FROM roles WHERE name = 'AGENT' LIMIT 1)
        WHERE role_id IS NULL
    """)
    
    # Drop old unique constraints on username and email (handle both constraints and indexes)
    # Get all unique constraints and indexes (refresh inspector after column additions)
    unique_constraints = {uc['name']: uc for uc in inspector.get_unique_constraints('users')}
    indexes = {idx['name']: idx for idx in inspector.get_indexes('users') if idx['unique']}
    
    # Try to drop username unique constraint/index
    if 'users_username_key' in unique_constraints:
        try:
            op.drop_constraint('users_username_key', 'users', type_='unique')
        except:
            pass
    elif 'users_username_key' in indexes:
        try:
            op.drop_index('users_username_key', table_name='users')
        except:
            pass
    
    # Try to drop email unique constraint/index
    if 'users_email_key' in unique_constraints:
        try:
            op.drop_constraint('users_email_key', 'users', type_='unique')
        except:
            pass
    elif 'users_email_key' in indexes:
        try:
            op.drop_index('users_email_key', table_name='users')
        except:
            pass
    
    # Create composite unique constraints for username and email with organization_id
    users_indexes = [idx['name'] for idx in inspector.get_indexes('users')]
    users_columns = [col["name"] for col in inspector.get_columns("users")]
    
    if 'ix_users_username_organization' not in users_indexes and 'organization_id' in users_columns:
        try:
            op.create_index('ix_users_username_organization', 'users', ['username', 'organization_id'], unique=True)
        except:
            pass
    if 'ix_users_email_organization' not in users_indexes and 'organization_id' in users_columns:
        try:
            op.create_index('ix_users_email_organization', 'users', ['email', 'organization_id'], unique=True)
        except:
            pass


def downgrade() -> None:
    # Drop composite unique indexes
    op.drop_index('ix_users_email_organization', table_name='users')
    op.drop_index('ix_users_username_organization', table_name='users')
    
    # Restore old unique constraints (if needed)
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.create_unique_constraint('users_username_key', 'users', ['username'])
    
    # Drop foreign keys and indexes
    op.drop_index('ix_users_role_id', table_name='users')
    op.drop_index('ix_users_organization_id', table_name='users')
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')
    op.drop_constraint('fk_users_organization_id', 'users', type_='foreignkey')
    
    # Drop columns from users
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'role_id')
    op.drop_column('users', 'organization_id')
    
    # Drop organizations table
    op.drop_index('ix_organizations_slug', table_name='organizations')
    op.drop_index('ix_organizations_name', table_name='organizations')
    op.drop_table('organizations')
    
    # Drop roles table
    op.drop_index('ix_roles_name', table_name='roles')
    op.drop_table('roles')

