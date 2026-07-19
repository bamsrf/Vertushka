"""Yandex-native enrichment (records вне Discogs)

Revision ID: 20260719_yandex_native
Revises: 20260715_radar_events
Create Date: 2026-07-19

Yandex Music как источник обогащения для релизов, которых нет в Discogs
(store-native, source='store'). Новой таблицы НЕ заводим — переиспользуем
Record. Добавляем аддитивно (nullable):
  records.yandex_album_id — внешний ключ альбома Yandex (аналог spotify_album_id)
  records.yandex_data     — cover/year/genre/tracklist (аналог discogs_data)

Идемпотентна. Полностью откатываема (drop колонок).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260719_yandex_native"
down_revision = "20260715_radar_events"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("records", "yandex_album_id"):
        op.add_column(
            "records",
            sa.Column("yandex_album_id", sa.String(64), nullable=True),
        )
    if not _has_column("records", "yandex_data"):
        op.add_column(
            "records",
            sa.Column("yandex_data", JSONB, nullable=True),
        )


def downgrade() -> None:
    if _has_column("records", "yandex_data"):
        op.drop_column("records", "yandex_data")
    if _has_column("records", "yandex_album_id"):
        op.drop_column("records", "yandex_album_id")
