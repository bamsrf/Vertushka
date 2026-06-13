"""User-submitted records (source='user')

Revision ID: 20260613_user_records
Revises: 20260613_token_version
Create Date: 2026-06-13

Третий источник записей — 'user'. Пластинка, которой нет ни в Discogs, ни в
Маркете: юзер добавляет вручную, запись проходит дабл-чек (preflight_dedup) и
становится общей после модерации. См. docs/plans/USER_SUBMITTED_RECORDS.md.

Новой таблицы НЕ заводим — user-record это Record с source='user'. Добавляем:
  records.created_by_user_id  — автор (модерация, права)
  records.moderation_status   — pending / approved / rejected / merged
  records.spotify_album_id    — связь с enrichment-источником
  records.user_submitted_data — сырой ввод (аналог discogs_data)
  индекс (source, moderation_status) — лента модерации
  users.is_staff              — доступ к admin-ленте модерации (§6)

Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260613_user_records"
down_revision = "20260613_token_version"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_index(table: str, index: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return index in {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if not _has_column("records", "created_by_user_id"):
        op.add_column(
            "records",
            sa.Column(
                "created_by_user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _has_column("records", "moderation_status"):
        op.add_column(
            "records",
            sa.Column(
                "moderation_status",
                sa.String(20),
                nullable=False,
                server_default="approved",
            ),
        )
        # Бэкфилл: все существующие discogs/store записи уже общие → approved.
        # server_default нужен только чтобы add_column на непустой таблице
        # не упал; для будущих source='user' дефолт ставится в коде ('pending').
    if not _has_column("records", "spotify_album_id"):
        op.add_column(
            "records",
            sa.Column("spotify_album_id", sa.String(64), nullable=True),
        )
    if not _has_column("records", "user_submitted_data"):
        op.add_column(
            "records",
            sa.Column("user_submitted_data", JSONB, nullable=True),
        )
    if not _has_index("records", "ix_records_source_moderation"):
        op.create_index(
            "ix_records_source_moderation",
            "records",
            ["source", "moderation_status"],
        )
    if not _has_column("users", "is_staff"):
        op.add_column(
            "users",
            sa.Column(
                "is_staff",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    if _has_index("records", "ix_records_source_moderation"):
        op.drop_index("ix_records_source_moderation", table_name="records")
    for col in ("user_submitted_data", "spotify_album_id", "moderation_status", "created_by_user_id"):
        if _has_column("records", col):
            op.drop_column("records", col)
    if _has_column("users", "is_staff"):
        op.drop_column("users", "is_staff")
