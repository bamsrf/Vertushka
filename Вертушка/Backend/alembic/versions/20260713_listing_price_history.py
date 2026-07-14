"""listing_price_history — снапшоты цены/статуса листингов (Волна B)

Пишется только при СМЕНЕ price или status (см. runner._upsert_listing) → соседние
строки на один listing = точки изменения. Отсюда:
- price_drop producer (LAG по captured_at ловит падение vs прошлой цены);
- будущий график динамики (Волна C, GET /records/{id}/price-history).
Ретеншн: чистим строки старше 1 года ночным cleanup-джобом.

Revision ID: 20260713_listing_price_history
Revises: 20260713_wishlist_item_notify
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260713_listing_price_history"
down_revision = "20260713_wishlist_item_notify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_price_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("store_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Денорм record_id — чтобы график/producer не джойнили store_listings.
        # SET NULL: история переживает отвязку/удаление записи.
        sa.Column(
            "record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("price_rub", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_price_history_record_time",
        "listing_price_history",
        ["record_id", "captured_at"],
    )
    op.create_index(
        "ix_price_history_listing_time",
        "listing_price_history",
        ["listing_id", "captured_at"],
    )
    # Для cleanup-джоба (DELETE WHERE captured_at < cutoff).
    op.create_index(
        "ix_price_history_captured",
        "listing_price_history",
        ["captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_history_captured", table_name="listing_price_history")
    op.drop_index("ix_price_history_listing_time", table_name="listing_price_history")
    op.drop_index("ix_price_history_record_time", table_name="listing_price_history")
    op.drop_table("listing_price_history")
