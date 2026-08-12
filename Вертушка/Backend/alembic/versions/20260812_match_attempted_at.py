"""store_listings.match_attempted_at — след неудачной попытки матчинга

До этой колонки неудача не оставляла следа. Очередь матчера бралась так:

    WHERE matched_record_id IS NULL ORDER BY first_seen_at ASC LIMIT 2000

Листинг, который не сматчился, оставался с `matched_record_id IS NULL` и тем
же `first_seen_at` — то есть на следующем прогоне снова попадал в ту же голову
очереди. Каждый час матчер перемалывал одни и те же безнадёжные позиции и
заново спрашивал про них Discogs: ~1 500 запросов в час на ~20 совпадений.

Хвост очереди при этом не двигался вовсе: у нового магазина rotaryrecords
впереди стояло 12 535 листингов, до его позиций не дошёл бы ни один запрос.

Теперь очередь сортируется по `match_attempted_at NULLS FIRST` — сначала те,
кого ни разу не пробовали (новые магазины попадают в матчер сразу), затем
самые давно пробованные. Плюс кулдаун: повтор не раньше чем через неделю.

Backfill намеренно НЕ делаем: NULL = «ни разу не пробовали» — ровно то, что
нужно. Один раз вся накопленная очередь пройдёт заново (это и требуется, чтобы
разобрать её честно), после чего кулдаун разведёт повторы во времени.

Индекс частичный (`WHERE matched_record_id IS NULL`) — вся очередь по
определению из несматченных, полный индекс на 400k строк был бы вчетверо
толще без пользы. CONCURRENTLY не используем: таблица небольшая, а deploy.sh
гонит миграции в транзакции.

Revision ID: 20260812_match_attempt
"""
import sqlalchemy as sa
from alembic import op

revision = "20260812_match_attempt"
down_revision = "20260810_click_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "store_listings",
        sa.Column("match_attempted_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_listing_match_queue",
        "store_listings",
        ["match_attempted_at", "first_seen_at"],
        postgresql_where=sa.text("matched_record_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_listing_match_queue", table_name="store_listings")
    op.drop_column("store_listings", "match_attempted_at")
