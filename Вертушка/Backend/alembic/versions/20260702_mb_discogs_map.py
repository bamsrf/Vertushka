"""Add mb_discogs_map + discogs_releases_index.cover_checked_at

Revision ID: 20260702_mb_map
Revises: 20260702_reports
Create Date: 2026-07-02

mb_discogs_map — офлайн-маппинг Discogs release ID → MusicBrainz MBID,
извлекается из MusicBrainz full-export dump (таблицы url, l_release_url,
release) скриптом app/scripts/ingest_mb_discogs_map.py. Даёт путь к обложкам
Cover Art Archive БЕЗ единого запроса к Discogs/MusicBrainz API:
  discogs_id → mbid → coverartarchive.org/release/{mbid}/front-1200

caa_checked_at — когда bulk-warm проверял наличие front-обложки в CAA
(включая промахи). NULL = ещё не проверяли.

cover_checked_at на discogs_releases_index — когда drip-воркер ходил в
Discogs API за обложкой этой строки (включая промахи). NULL = не ходил.
Добавление nullable-колонки на ~16M строк — metadata-only, мгновенно.

Частичный индекс для drip-кандидатов создаётся CONCURRENTLY в
autocommit_block (в обычной txn Alembic он бы лочил таблицу).

Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260702_mb_map"
down_revision = "20260702_reports"
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

    if not _table_exists(conn, "mb_discogs_map"):
        op.create_table(
            "mb_discogs_map",
            sa.Column("discogs_id", sa.BigInteger, primary_key=True),
            sa.Column("mbid", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
            # Есть ли front-обложка в CAA — известно офлайн из
            # mbdump-cover-art-archive (таблицы cover_art + cover_art_type).
            sa.Column("has_front", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("caa_checked_at", sa.DateTime, nullable=True),
        )
        op.create_index(
            "ix_mb_discogs_map_unchecked",
            "mb_discogs_map",
            ["discogs_id"],
            postgresql_where=sa.text("caa_checked_at IS NULL"),
        )

    if _table_exists(conn, "discogs_releases_index") and not _column_exists(
        conn, "discogs_releases_index", "cover_checked_at"
    ):
        op.add_column(
            "discogs_releases_index",
            sa.Column("cover_checked_at", sa.DateTime, nullable=True),
        )

    # Индекс кандидатов drip-воркера: строки без обложки, куда ещё не ходили.
    # CONCURRENTLY — таблица боевая, обычный CREATE INDEX держал бы её под локом.
    if _table_exists(conn, "discogs_releases_index"):
        with op.get_context().autocommit_block():
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "ix_dri_drip_candidates ON discogs_releases_index (year DESC NULLS LAST) "
                "WHERE cover_image_url IS NULL AND cover_checked_at IS NULL"
            )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_dri_drip_candidates")
    op.execute("ALTER TABLE discogs_releases_index DROP COLUMN IF EXISTS cover_checked_at")
    op.execute("DROP TABLE IF EXISTS mb_discogs_map CASCADE")
