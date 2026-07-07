"""discogs_master_covers: доп-ключи источника (Deezer album id, md5, source)

Backfill обложек по Deezer/iTunes хранит внешние ключи для будущего
resize/дедупа и происхождения обложки. Все nullable — старые строки не трогаем.

Revision ID: 20260707_cover_backfill
Revises: 20260703_master_covers
"""
from alembic import op

revision = "20260707_cover_backfill"
down_revision = "20260703_master_covers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE discogs_master_covers "
        "ADD COLUMN IF NOT EXISTS deezer_album_id BIGINT, "
        "ADD COLUMN IF NOT EXISTS image_md5 TEXT, "
        "ADD COLUMN IF NOT EXISTS source TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE discogs_master_covers "
        "DROP COLUMN IF EXISTS deezer_album_id, "
        "DROP COLUMN IF EXISTS image_md5, "
        "DROP COLUMN IF EXISTS source"
    )
