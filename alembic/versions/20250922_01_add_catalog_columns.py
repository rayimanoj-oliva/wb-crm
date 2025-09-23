"""add image_url to categories and stock/image_url to products

Revision ID: add_catalog_columns_20250922
Revises: 
Create Date: 2025-09-22
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_catalog_columns_20250922'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('image_url', sa.String(length=500), nullable=True))
    op.add_column('products', sa.Column('image_url', sa.String(length=500), nullable=True))
    op.add_column('products', sa.Column('stock', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('products', 'stock', server_default=None)


def downgrade() -> None:
    op.drop_column('products', 'stock')
    op.drop_column('products', 'image_url')
    op.drop_column('categories', 'image_url')


