"""merge org_id and admin migrations

Revision ID: b9be422245eb
Revises: add_org_id_to_all_tables, migrate_admin_to_org_admin
Create Date: 2025-12-31 13:39:20.187615

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9be422245eb'
down_revision: Union[str, None] = ('add_org_id_to_all_tables', 'migrate_admin_to_org_admin')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
