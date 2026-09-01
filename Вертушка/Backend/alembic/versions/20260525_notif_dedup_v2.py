"""Notifications v2: dedup_key + bumped_at + occurrences + snoozed_until + priority

Revision ID: 20260525_notif_v2
Revises: 20260525_merge
Create Date: 2026-05-25

См. docs/plans/social/PLAN_NOTIFICATIONS_V2.md — Волна B-1.
Готовит схему под bump-or-create логику и snooze ladder.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260525_notif_v2"
down_revision: Union[str, tuple, None] = "20260525_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("dedup_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("bumped_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "notifications",
        sa.Column("snoozed_until", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="2"),
    )

    # Backfill dedup_key из (type, entity_id). Где entity_id нет (или несколько на тип),
    # уникальность даст id-постфикс — это нормально, на read оно не активно.
    op.execute(
        """
        UPDATE notifications
        SET dedup_key = type || ':' || COALESCE(entity_id, id::text)
        WHERE dedup_key IS NULL;
        """
    )
    op.execute(
        "UPDATE notifications SET bumped_at = created_at WHERE bumped_at IS NULL;"
    )

    # Перед уникальным индексом — схлопнуть дубликаты unread на (user, dedup_key):
    # оставляем самую свежую запись, остальные помечаем как прочитанные сейчас.
    # Это финализирует Волну A: старые дубли «снова в продаже» уходят из unread.
    op.execute(
        """
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY user_id, dedup_key
            ORDER BY created_at DESC
          ) AS rn
          FROM notifications
          WHERE read_at IS NULL
        )
        UPDATE notifications n
        SET read_at = NOW()
        FROM ranked r
        WHERE r.id = n.id AND r.rn > 1;
        """
    )

    op.alter_column("notifications", "dedup_key", nullable=False)
    op.alter_column("notifications", "bumped_at", nullable=False)

    # Один активный (unread) алерт на ключ (user_id, dedup_key).
    op.create_index(
        "ix_notifications_user_dedup_unread",
        "notifications",
        ["user_id", "dedup_key"],
        unique=True,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_snooze",
        "notifications",
        ["user_id", "dedup_key", "snoozed_until"],
    )
    # Сортировка ленты по bumped_at: bump-aware ordering.
    op.create_index(
        "ix_notifications_user_bumped",
        "notifications",
        ["user_id", "bumped_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_bumped", table_name="notifications")
    op.drop_index("ix_notifications_snooze", table_name="notifications")
    op.drop_index("ix_notifications_user_dedup_unread", table_name="notifications")
    op.drop_column("notifications", "priority")
    op.drop_column("notifications", "snoozed_until")
    op.drop_column("notifications", "occurrences")
    op.drop_column("notifications", "bumped_at")
    op.drop_column("notifications", "dedup_key")
