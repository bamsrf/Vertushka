"""waitlist_entries.notified_at — отметка о разосланной ссылке на стор

Waitlist собирался ровно ради одного письма: «вышли — вот ссылка». Пока
рассылки не было, таблице хватало email + source. Теперь рассылка идёт
пачками (scripts/send_waitlist_launch_email.py), а падение посередине не
должно приводить к повторным письмам тем, кому уже отправили.

Отметка ставится на все строки с этим email: один человек мог подписаться
с нескольких профилей (email + source не уникальны), а письмо ему нужно
одно.

Revision ID: 20260901_waitlist_notified
Revises: 20260825_profile_shared_at
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260901_waitlist_notified"
down_revision = "20260825_profile_shared_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "waitlist_entries",
        sa.Column("notified_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("waitlist_entries", "notified_at")
