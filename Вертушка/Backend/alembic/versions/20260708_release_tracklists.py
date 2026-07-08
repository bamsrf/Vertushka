"""discogs_release_tracklists — локальные треклисты (Tier 2, main-release мастеров)

Slim-дамп треклист не несёт → деталь версии тянула его live (MB/Deezer/Discogs).
Эта таблица держит треклисты представитель-релизов мастеров (~2.3M), спарсенные
из Discogs releases dump → деталь мгновенна, ноль внешних вызовов. Только
main-release (не все 13M версий) — диск прода тесный (7.2GB свободно).

Revision ID: 20260708_release_tracklists
Revises: 20260707_cover_backfill
"""
from alembic import op

revision = "20260708_release_tracklists"
down_revision = "20260707_cover_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS discogs_release_tracklists ("
        "  discogs_id BIGINT PRIMARY KEY, "
        "  tracklist  JSONB NOT NULL, "
        "  created_at TIMESTAMP NOT NULL DEFAULT now()"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discogs_release_tracklists")
