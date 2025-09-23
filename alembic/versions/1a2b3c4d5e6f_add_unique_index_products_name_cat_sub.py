"""
Add unique index on products(lower(name), category_id, sub_category_id)

Revision ID: 1a2b3c4d5e6f
Revises: fb3eca9b4349
Create Date: 2025-09-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = 'fb3eca9b4349'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Remove duplicates keeping the earliest created_at per (lower(name), category_id, sub_category_id)
    #    Use IS NOT DISTINCT FROM to treat NULLs as equal for sub_category_id
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY lower(name), category_id, sub_category_id
                    ORDER BY created_at ASC, id ASC
                ) AS rn
            FROM products
        )
        DELETE FROM products p
        USING ranked r
        WHERE p.id = r.id AND r.rn > 1;
        """
    )

    # 2) Create unique index
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_products_name_cat_sub_lower
        ON products (lower(name), category_id, sub_category_id);
        """
    )


def downgrade():
    op.execute(
        """
        DROP INDEX IF EXISTS uq_products_name_cat_sub_lower;
        """
    )

