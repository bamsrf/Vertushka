"""Add discogs_artist_names — derived distinct-name set for artist-search filter.

Поиск артистов (`/artists/search`) отдаёт Discogs-результаты, среди которых много
мусорных тёзок/фан-аккаунтов с 0 релизов. У дамп-индекса `discogs_releases_index`
нет artist_id (только имя + GIN trigram), а `lower(artist) = ANY(...)` по 13M строк
делает Seq Scan ~4с. Поэтому держим производную таблицу distinct `lower(artist)`
с btree PK — membership-проверка имени уходит в index-scan (sub-ms), без единого
вызова Discogs API. Имя есть → у артиста есть релизы → оставляем; нет → дроп.

Поддерживается в свежем виде: ingest дампа и live-upsert релиза доливают имя.

Revision ID: 20260629_artist_names
Revises: 20260623_gift_recipient
"""
from alembic import op


revision = "20260629_artist_names"
down_revision = "20260623_gift_recipient"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discogs_artist_names (
            name_norm text PRIMARY KEY
        )
        """
    )
    # Первичное наполнение из существующего индекса. ~2M distinct из 13M строк,
    # один проход; ON CONFLICT для идемпотентности при повторном прогоне.
    op.execute(
        """
        INSERT INTO discogs_artist_names (name_norm)
        SELECT DISTINCT lower(artist)
        FROM discogs_releases_index
        WHERE artist IS NOT NULL AND artist <> ''
        ON CONFLICT (name_norm) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discogs_artist_names")
