"""Переезд DDL/бэкфилла из init_db в миграцию.

Эти ALTER/CREATE INDEX/UPDATE годами выполнялись на КАЖДОМ старте приложения
(app/database.py::init_db) под statement_timeout=30s. На проде они давно
применены и превращались в no-op'ы, но UPDATE-бэкфилл gift_bookings бежал по
таблице заново при каждом рестарте — с ростом данных это гарантированный
таймаут старта. Здесь они выполняются один раз, как и положено миграции.

Всё идемпотентно (IF NOT EXISTS / WHERE ... IS NULL): на проде, где init_db
уже всё создал, миграция пройдёт мгновенно и ничего не изменит.

downgrade — no-op намеренно: колонки существовали до этой миграции (их
создавал init_db), и «откатить» их значило бы удалить чужие данные.

Revision ID: 20260819_startup_ddl
Revises: 20260818_apple_revoke
Create Date: 2026-08-19
"""
from alembic import op

revision = "20260819_startup_ddl"
down_revision = "20260818_apple_revoke"
branch_labels = None
depends_on = None

_STATEMENTS = [
    "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
    "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMP",
    "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS match_dismissed_at TIMESTAMP",
    "ALTER TABLE gift_bookings ADD COLUMN IF NOT EXISTS record_id UUID REFERENCES records(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_gift_bookings_record_id ON gift_bookings (record_id)",
    # Бэкфилл для живых броней: у них связь с пунктом вишлиста ещё цела.
    # У завершённых её нет — там колонка останется пустой, и такие
    # подарки в «Я дарю» не покажутся (данных для них просто не сохранилось).
    """
    UPDATE gift_bookings b
       SET record_id = wi.record_id
      FROM wishlist_items wi
     WHERE b.wishlist_item_id = wi.id
       AND b.record_id IS NULL
    """,
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_follow_request BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_wishlist_in_stock BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_achievement BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_gift_confirmed BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_milestone BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_hours_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_hours_start TIME",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_hours_end TIME",
]


def upgrade() -> None:
    for sql in _STATEMENTS:
        op.execute(sql)


def downgrade() -> None:
    # См. докстринг: колонки старше миграции, откатывать нечего.
    pass
