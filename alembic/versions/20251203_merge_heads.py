"""
Merge multiple heads: facebook_template_id and wa_api_log

Revision ID: 20251203_merge_heads
Revises: 20251203_add_facebook_template_id, 20251128_add_wa_api_log
Create Date: 2025-12-03 12:30:00
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20251203_merge_heads"
down_revision: tuple = ("20251203_add_facebook_template_id", "20251128_add_wa_api_log")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
