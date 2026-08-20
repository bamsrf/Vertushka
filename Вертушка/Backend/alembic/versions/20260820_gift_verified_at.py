"""gift_bookings.verified_at — подтверждённое владение email дарителя

Раздел «Я дарю» матчит анонимные брони к аккаунту по gifter_email, а это
произвольная строка из публичной формы (валидируется только формат). Спуф
чужого email позволял подсунуть жертве фантомный «подарок» вместе с
cancel_token (можно отменить чужую бронь) и личностью получателя.

verified_at проставляется в PUT /gifts/{id}/confirm при переходе
PENDING → BOOKED по verify_token — то есть только когда владелец почты
реально кликнул ссылку из письма. Email-ветка «Я дарю» теперь отдаёт
только такие брони.

Бэкфилла нет намеренно: у существующих броней владение email никогда не
проверялось (флаг верификации выключен), считать их подтверждёнными нельзя —
это ровно та дыра, которую закрываем. Свои брони пользователей продолжают
показываться через booked_by_user_id.

Revision ID: 20260820_gift_verified_at
Revises: 20260819_startup_ddl
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "20260820_gift_verified_at"
down_revision = "20260820_wishlist_gift_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gift_bookings",
        sa.Column("verified_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gift_bookings", "verified_at")
