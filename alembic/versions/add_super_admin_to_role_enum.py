"""Add SUPER_ADMIN to user_role_enum

Revision ID: add_super_admin_enum
Revises: add_orgs_roles_2024
Create Date: 2024-12-19 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_super_admin_enum'
down_revision: Union[str, None] = 'add_orgs_roles_2024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add SUPER_ADMIN to the existing user_role_enum
    # PostgreSQL allows adding values to enum types (in PostgreSQL 9.1+)
    # We use a DO block to check if it exists first to make it idempotent
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'SUPER_ADMIN' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'user_role_enum')
            ) THEN
                ALTER TYPE user_role_enum ADD VALUE 'SUPER_ADMIN';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type, which is complex
    # For now, we'll leave it as a no-op
    pass

