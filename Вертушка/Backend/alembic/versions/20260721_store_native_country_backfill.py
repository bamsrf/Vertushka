"""backfill: store-native records с кириллицей → country='Russia'

Store-native запись (source='store', discogs_id=NULL) создаётся, когда Discogs
релиз не знает — напр. «Антоха МС – Родня», кастом только внутри Коробки Винила.
Раньше country не проставлялся (NULL), из-за чего is_local_country=False и
валюация шла мимо российской ветки. Кириллица в artist/title — уверенный сигнал
российского релиза (кириллический артист не из Discogs почти всегда РФ-инди).

Новые записи получают country='Russia' в _create_store_native_record; эта
миграция дотягивает уже созданные. Только там, где country ещё пуст — легитимно
проставленную страну не перетираем.

Revision ID: 20260721_store_native_country
Revises: 20260714_wl_conditions
"""
from alembic import op

revision = "20260721_store_native_country"
down_revision = "20260714_wl_conditions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE records
        SET country = 'Russia'
        WHERE source = 'store'
          AND country IS NULL
          AND (artist ~ '[а-яёА-ЯЁ]' OR title ~ '[а-яёА-ЯЁ]')
        """
    )


def downgrade() -> None:
    # Необратимая data-миграция: до апгрейда country у этих записей был NULL,
    # но откатывать в NULL опасно — можем занулить страну, проставленную позже
    # по другой причине. Оставляем как есть.
    pass
