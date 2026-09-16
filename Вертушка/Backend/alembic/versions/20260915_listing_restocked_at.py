"""store_listings.restocked_at — возврат позиции в наличие

«Новинки» и сортировка «сначала свежие» считались по first_seen_at, то есть по
дате первого показа листинга. Магазин, который перезавозит те же наименования
под тем же external_id, новых строк не создаёт — first_seen остаётся датой
онбординга, и витрина показывает старьё как новинки (Коробка Винила: самый
свежий видимый листинг 23 мая при живом перезавозе ~700 позиций).

Поле отдельное, а не перезапись first_seen_at: на исходный возраст листинга
опираются очередь матчера и гейт persistence у store-native.

Матвью пересоздаётся: new_today_count теперь считает по
GREATEST(first_seen_at, restocked_at). Остальные FILTER-условия не тронуты —
они обязаны совпадать 1:1 с live-запросами в market.py.

Revision ID: 20260915_restocked_at
Revises: 20260915_master_mirror
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa


revision = "20260915_restocked_at"
down_revision = "20260915_master_mirror"
branch_labels = None
depends_on = None


# Свежесть для витрины: появился ИЛИ вернулся в наличие. NULL в GREATEST
# Postgres игнорирует, так что у листинга без перезавоза это first_seen_at.
_FRESH = "GREATEST(sl.first_seen_at, sl.restocked_at)"

_MV_BODY = """
SELECT
    s.id AS store_id,
    s.slug,
    s.name,
    s.logo_url,
    s.rating,
    COUNT(sl.id) FILTER (
        WHERE sl.status = 'in_stock'
          AND sl.last_seen_at >= NOW() - INTERVAL '7 days'
          AND sl.matched_record_id IS NOT NULL
          AND sl.price_rub IS NOT NULL
          AND r.merged_into_id IS NULL
          AND COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload->>'image_url') IS NOT NULL
    ) AS in_stock_count,
    AVG(sl.price_rub) FILTER (
        WHERE sl.status = 'in_stock'
          AND sl.last_seen_at >= NOW() - INTERVAL '7 days'
          AND sl.price_rub IS NOT NULL
          AND sl.matched_record_id IS NOT NULL
          AND r.merged_into_id IS NULL
    ) AS avg_price_rub,
    COUNT(sl.id) FILTER (
        WHERE sl.status = 'in_stock'
          AND {fresh} >= NOW() - INTERVAL '24 hours'
          AND sl.matched_record_id IS NOT NULL
          AND sl.price_rub IS NOT NULL
          AND r.merged_into_id IS NULL
          AND COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload->>'image_url') IS NOT NULL
    ) AS new_today_count
FROM stores s
LEFT JOIN store_listings sl ON sl.store_id = s.id
LEFT JOIN records r ON r.id = sl.matched_record_id
WHERE s.is_active = true
GROUP BY s.id;
"""

_OLD_NEW_TODAY = "sl.first_seen_at"

_CREATE_IDX = (
    "CREATE UNIQUE INDEX ix_market_store_stats_store_id "
    "ON market_store_stats (store_id);"
)


def _recreate_mv(fresh_expr: str) -> None:
    # CASCADE не нужен: на матвью ничего не висит, но DROP обязателен —
    # CREATE OR REPLACE для materialized view Postgres не умеет.
    op.execute("DROP MATERIALIZED VIEW IF EXISTS market_store_stats;")
    op.execute(
        "CREATE MATERIALIZED VIEW market_store_stats AS"
        + _MV_BODY.format(fresh=fresh_expr)
    )
    op.execute(_CREATE_IDX)


def upgrade() -> None:
    op.add_column(
        "store_listings",
        sa.Column("restocked_at", sa.DateTime(), nullable=True),
    )
    # Сортировка витрины по свежести идёт внутри уже отфильтрованных по
    # магазину/наличию выборок, но «Новинки» и глобальная карусель сортируют
    # весь маркет — функциональный индекс держит их на прежней стоимости.
    op.execute(
        "CREATE INDEX ix_listing_fresh_at ON store_listings "
        "(GREATEST(first_seen_at, restocked_at) DESC) "
        "WHERE status = 'in_stock' AND matched_record_id IS NOT NULL;"
    )
    # Бэкфилл из журнала переходов. Без него поле заполнялось бы только
    # будущими перезавозами, и витрина осталась бы неправильной до первого
    # ухода каждой позиции из наличия — то есть недели. Журнал годится:
    # _upsert_listing пишет точку на каждую смену статуса, а ретеншн
    # listing_price_history — год, то есть вся история маркета.
    #
    # Первая точка листинга (prev_status IS NULL) — это его появление, а не
    # перезавоз: она и есть first_seen_at, второй раз её учитывать нельзя.
    op.execute(
        """
        WITH seq AS (
            SELECT listing_id,
                   status,
                   captured_at,
                   LAG(status) OVER (
                       PARTITION BY listing_id ORDER BY captured_at, id
                   ) AS prev_status
            FROM listing_price_history
        ),
        restocks AS (
            SELECT listing_id, MAX(captured_at) AS restocked_at
            FROM seq
            WHERE status = 'in_stock'
              AND prev_status IS NOT NULL
              AND prev_status <> 'in_stock'
            GROUP BY listing_id
        )
        UPDATE store_listings sl
        SET restocked_at = r.restocked_at
        FROM restocks r
        WHERE r.listing_id = sl.id;
        """
    )
    _recreate_mv(_FRESH)


def downgrade() -> None:
    _recreate_mv(_OLD_NEW_TODAY)
    op.execute("DROP INDEX IF EXISTS ix_listing_fresh_at;")
    op.drop_column("store_listings", "restocked_at")
