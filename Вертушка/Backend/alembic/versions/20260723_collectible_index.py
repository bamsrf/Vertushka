"""Add discogs_releases_index.is_collectible + collectible_checked_at

Revision ID: 20260723_collectible_idx
Revises: 20260721_merge_heads
Create Date: 2026-07-23

Экран версий считал is_collectible через get_release на КАЖДУЮ невиданную версию
(~100 вызовов Discogs на страницу в 50 версий при глобальном окне 60/мин). Флаг
при этом жил только в Redis (master_versions_enriched, TTL 3 дня) — после
истечения всё считалось заново.

Эти две колонки делают флаг durable-свойством релиза: посчитан однажды —
читается из дампа бесплатно, в том же SELECT, что и остальные поля версии.
collectible_checked_at отделяет «проверено, не редкий» (false) от «ещё не
проверяли» (NULL) — без этого отрицательный результат перепроверялся бы вечно.

DEFAULT-less nullable колонки на 13M строк — metadata-only, мгновенно.
Идемпотентна.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260723_collectible_idx"
down_revision = "20260721_merge_heads"
branch_labels = None
depends_on = None


def _has_column(conn, column: str) -> bool:
    return bool(conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'discogs_releases_index' "
        "AND column_name = :col)"
    ), {"col": column}).scalar())


def upgrade() -> None:
    conn = op.get_bind()
    table_exists = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = 'discogs_releases_index')"
    )).scalar()
    if not table_exists:
        return

    if not _has_column(conn, "is_collectible"):
        op.add_column(
            "discogs_releases_index",
            sa.Column("is_collectible", sa.Boolean, nullable=True),
        )
    if not _has_column(conn, "collectible_checked_at"):
        op.add_column(
            "discogs_releases_index",
            sa.Column("collectible_checked_at", sa.DateTime, nullable=True),
        )


def downgrade() -> None:
    op.execute("ALTER TABLE discogs_releases_index DROP COLUMN IF EXISTS collectible_checked_at")
    op.execute("ALTER TABLE discogs_releases_index DROP COLUMN IF EXISTS is_collectible")
