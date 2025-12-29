"""Add code column to organizations table

Revision ID: add_code_to_orgs
Revises: add_super_admin_enum
Create Date: 2024-12-29 13:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_code_to_orgs'
down_revision: Union[str, None] = 'add_super_admin_enum'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add code column to organizations table
    op.add_column('organizations', sa.Column('code', sa.String(length=50), nullable=True))
    
    # Create unique index on code
    op.create_index('ix_organizations_code', 'organizations', ['code'], unique=True)


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_organizations_code', table_name='organizations')
    
    # Drop code column
    op.drop_column('organizations', 'code')

