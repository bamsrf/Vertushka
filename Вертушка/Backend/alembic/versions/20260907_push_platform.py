"""users.push_platform — платформа устройства, с которого пришёл push-токен

Раньше токен был безликим: по строке ExponentPushToken[...] не понять, iOS
это или Android. Для Android-порта нужно различать платформы в статистике
доставки и при отладке (notification channel есть только на Android).

Nullable: iOS 1.0.0/1.0.1 поле не шлют, а у них токены уже записаны.
Один токен на юзера (last-wins) — сознательно, см. ANDROID_PORT_PLAN.md WS2.

Revision ID: 20260907_push_platform
Revises: 20260901_waitlist_notified
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260907_push_platform"
down_revision = "20260901_waitlist_notified"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("push_platform", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "push_platform")
