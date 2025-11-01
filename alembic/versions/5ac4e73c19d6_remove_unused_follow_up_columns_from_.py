"""remove unused follow_up columns from customers

Revision ID: 5ac4e73c19d6
Revises: d7669e22858c
Create Date: 2025-10-31 16:17:28.234537

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ac4e73c19d6'
down_revision: Union[str, None] = 'd7669e22858c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Remove unused follow_up columns from customers table."""
    from sqlalchemy import inspect
    
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("customers")]
    
    # Drop follow_up_step if it exists
    if "follow_up_step" in existing_columns:
        op.drop_column('customers', 'follow_up_step')
    
    # Drop follow_up_status if it exists
    if "follow_up_status" in existing_columns:
        op.drop_column('customers', 'follow_up_status')


def downgrade() -> None:
    """Downgrade schema - Re-add follow_up columns (not recommended)."""
    # Note: We don't know the original column definitions, so this is a placeholder
    # If you need to rollback, you'll need to define the original column structure
    pass
