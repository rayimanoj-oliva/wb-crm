"""Migrate ADMIN users to ORG_ADMIN role

Revision ID: migrate_admin_to_org_admin
Revises: add_super_admin_enum
Create Date: 2025-01-27 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'migrate_admin_to_org_admin'
down_revision: Union[str, None] = 'add_super_admin_enum'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate all existing ADMIN users to ORG_ADMIN role.
    This updates the role_id field to point to the ORG_ADMIN role.
    """
    # Get the ORG_ADMIN role ID
    # Update all users with role='ADMIN' to have role_id pointing to ORG_ADMIN
    op.execute("""
        UPDATE users 
        SET role_id = (SELECT id FROM roles WHERE name = 'ORG_ADMIN' LIMIT 1)
        WHERE role = 'ADMIN' 
        AND role_id IS NULL;
    """)
    
    # Also update users that might already have a role_id but still have legacy role='ADMIN'
    # This ensures consistency
    op.execute("""
        UPDATE users 
        SET role_id = (SELECT id FROM roles WHERE name = 'ORG_ADMIN' LIMIT 1)
        WHERE role = 'ADMIN' 
        AND (role_id IS NULL OR role_id != (SELECT id FROM roles WHERE name = 'ORG_ADMIN' LIMIT 1));
    """)


def downgrade() -> None:
    """
    Note: This migration is not easily reversible as we don't know which users
    were originally ADMIN vs ORG_ADMIN. This is a one-way migration.
    """
    # We could potentially set role_id back to NULL for users that were migrated,
    # but we don't have a reliable way to identify which users were migrated
    # vs which were created as ORG_ADMIN from the start.
    pass

