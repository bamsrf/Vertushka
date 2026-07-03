"""Add discogs_artists + discogs_releases_index.artist_ids

Revision ID: 20260703_artist_map
Revises: 20260702_mb_map
Create Date: 2026-07-03

Закрывает брешь артистов: экран артиста строил дискографию живыми вызовами
Discogs (/artists/{id}/releases + Search + master_info фан-аут), потому что
slim-индекс хранил имя артиста текстом без ID.

discogs_artists — id→name из artists-дампа (~9M строк, для имени артиста
без API). artist_ids BIGINT[] на индексе — основные артисты релиза (не
extraartists) из releases-дампа. GIN-индекс по artist_ids даёт локальную
дискографию: WHERE artist_ids @> ARRAY[id].

Данные грузит app/scripts/load_artist_map.py из CSV, приготовленных локально
app/scripts/extract_discogs_artist_map.py. GIN строится ПОСЛЕ backfill'а
самим загрузчиком (на пустой колонке он бессмыслен, после UPDATE — быстрее
одним проходом); здесь только колонка и таблица.

Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260703_artist_map"
down_revision = "20260702_mb_map"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :name)"
        ),
        {"name": name},
    ).scalar())


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": column},
    ).scalar())


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "discogs_artists"):
        op.create_table(
            "discogs_artists",
            sa.Column("artist_id", sa.BigInteger, primary_key=True),
            sa.Column("name", sa.Text, nullable=False),
        )

    if _table_exists(conn, "discogs_releases_index") and not _column_exists(
        conn, "discogs_releases_index", "artist_ids"
    ):
        op.add_column(
            "discogs_releases_index",
            sa.Column("artist_ids", sa.dialects.postgresql.ARRAY(sa.BigInteger), nullable=True),
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_dri_artist_ids")
    op.execute("ALTER TABLE discogs_releases_index DROP COLUMN IF EXISTS artist_ids")
    op.execute("DROP TABLE IF EXISTS discogs_artists CASCADE")
