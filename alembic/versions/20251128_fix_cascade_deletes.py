"""
Fix CASCADE deletes for campaign related tables

Revision ID: 20251128_fix_cascade_deletes
Revises: 20251127_add_flow_sched
Create Date: 2025-11-28
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251128_fix_cascade_deletes"
down_revision: Union[str, None] = "20251127_add_flow_sched"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix campaign_customers table - add CASCADE on delete
    op.execute("""
        ALTER TABLE campaign_customers
        DROP CONSTRAINT IF EXISTS campaign_customers_campaign_id_fkey;
    """)
    op.execute("""
        ALTER TABLE campaign_customers
        ADD CONSTRAINT campaign_customers_campaign_id_fkey
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE;
    """)

    op.execute("""
        ALTER TABLE campaign_customers
        DROP CONSTRAINT IF EXISTS campaign_customers_customer_id_fkey;
    """)
    op.execute("""
        ALTER TABLE campaign_customers
        ADD CONSTRAINT campaign_customers_customer_id_fkey
        FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE;
    """)


def downgrade() -> None:
    # Revert to no CASCADE
    op.execute("""
        ALTER TABLE campaign_customers
        DROP CONSTRAINT IF EXISTS campaign_customers_campaign_id_fkey;
    """)
    op.execute("""
        ALTER TABLE campaign_customers
        ADD CONSTRAINT campaign_customers_campaign_id_fkey
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id);
    """)

    op.execute("""
        ALTER TABLE campaign_customers
        DROP CONSTRAINT IF EXISTS campaign_customers_customer_id_fkey;
    """)
    op.execute("""
        ALTER TABLE campaign_customers
        ADD CONSTRAINT campaign_customers_customer_id_fkey
        FOREIGN KEY (customer_id) REFERENCES customers(id);
    """)
