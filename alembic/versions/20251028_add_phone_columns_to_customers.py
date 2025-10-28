"""add phone_1 and phone_2 columns to customers

Revision ID: 20251028_add_phone_columns
Revises: c36560c449a0
Create Date: 2025-10-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20251028_add_phone_columns'
down_revision: Union[str, None] = 'c36560c449a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add phone_1 and phone_2 to customers."""
    with op.batch_alter_table('customers') as batch_op:
        batch_op.add_column(sa.Column('phone_1', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('phone_2', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema: drop phone_1 and phone_2 from customers."""
    with op.batch_alter_table('customers') as batch_op:
        batch_op.drop_column('phone_2')
        batch_op.drop_column('phone_1')


