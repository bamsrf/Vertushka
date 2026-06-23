"""Add recipient_user_id to gift_bookings (anti-farm anchor for J3/J4 + social).

Получатель подарка = владелец вишлиста. При завершении брони
(complete_gift_booking) wishlist_item_id обнуляется, поэтому связь
получатель↔бронь теряется. Денормализуем recipient_user_id, чтобы
evaluator-ы серии «Дарящая рука» (распределение по разным получателям,
Бумеранг, Любимчик) могли считать историю после COMPLETED.

Revision ID: 20260623_gift_recipient
Revises: 20260617_approve_user_records
"""
import sqlalchemy as sa
from alembic import op

revision = "20260623_gift_recipient"
down_revision = "20260617_approve_user_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gift_bookings",
        sa.Column("recipient_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_gift_bookings_recipient_user_id",
        "gift_bookings",
        ["recipient_user_id"],
    )
    op.create_foreign_key(
        "fk_gift_bookings_recipient_user_id",
        "gift_bookings",
        "users",
        ["recipient_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Бэкфилл активных броней (PENDING/BOOKED) — получатель ещё известен через
    # wishlist_item → wishlist.user_id. COMPLETED уже отвязаны (wishlist_item_id
    # IS NULL), их историю не восстанавливаем — anti-farm стартует с нуля.
    op.execute(
        """
        UPDATE gift_bookings gb
        SET recipient_user_id = w.user_id
        FROM wishlist_items wi
        JOIN wishlists w ON w.id = wi.wishlist_id
        WHERE gb.wishlist_item_id = wi.id
          AND gb.recipient_user_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_gift_bookings_recipient_user_id", "gift_bookings", type_="foreignkey"
    )
    op.drop_index("ix_gift_bookings_recipient_user_id", table_name="gift_bookings")
    op.drop_column("gift_bookings", "recipient_user_id")
