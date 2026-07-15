"""wishlist_items.conditions — принятые грейды состояния для радара

Радар-фича: юзер в меню порога отмечает, какие копии считать (Sealed / M-NM / VG+ / VG).
Фильтрует «самую низкую подходящую цену» и статус на радаре. NULL = любое состояние.
Значения: 'sealed', 'mint', 'vg_plus', 'vg'.

Revision ID: 20260714_wishlist_item_conditions
Revises: 20260713_listing_price_history
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260714_wishlist_item_conditions"
down_revision = "20260713_listing_price_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist_items",
        sa.Column("conditions", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "conditions")
