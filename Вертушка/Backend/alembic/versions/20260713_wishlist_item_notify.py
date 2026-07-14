"""wishlist_items.notify_mode + price_threshold_rub — per-item колокольчик

Волна A из docs/plans/PLAN_WISHLIST_PRICE_ALERTS.md.
- notify_mode: 'watched' (дефолт, тихо + недельный digest) | 'subscribed' (bell → push).
- price_threshold_rub: опциональный порог «уведомить, когда дешевле X».
  Колонку заводим сразу (дёшево), UI-поповер порога включаем в Волне B.
Partial index по subscribed-item'ам ускоряет producer'у выборку «на кого слать push».

Revision ID: 20260713_wishlist_item_notify
Revises: 20260708_release_tracklists
"""
import sqlalchemy as sa
from alembic import op

revision = "20260713_wishlist_item_notify"
down_revision = "20260708_release_tracklists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist_items",
        sa.Column(
            "notify_mode",
            sa.String(16),
            nullable=False,
            server_default="watched",
        ),
    )
    op.add_column(
        "wishlist_items",
        sa.Column(
            "price_threshold_rub",
            sa.Numeric(12, 2),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_wishlist_items_subscribed_record",
        "wishlist_items",
        ["record_id"],
        postgresql_where=sa.text("notify_mode = 'subscribed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_wishlist_items_subscribed_record", table_name="wishlist_items")
    op.drop_column("wishlist_items", "price_threshold_rub")
    op.drop_column("wishlist_items", "notify_mode")
