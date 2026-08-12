"""Сводка здоровья Маркета: по магазину + по общим конвейерам.

Зачем. За 12.08 нашлось три поломки, каждая из которых молчала неделями и
обнаружилась только когда пришли смотреть руками:

  * очередь матчинга стояла — новый магазин не получил ни одного запроса,
    потому что впереди него навсегда застряли 12 535 чужих листингов;
  * vinyl.ru не обновлялся 48 дней при зелёном статусе;
  * харвест обложек три недели лежал за `return` и выбрасывал уже скачанные
    картинки — 4 727 записей остались без обложки.

Общее у них одно: **никто не сигналил**. С ростом числа магазинов ловить такое
вручную перестанет работать, поэтому отчёт считает не «всё хорошо», а
конкретные признаки застоя и называет их словами.

Используется двумя потребителями: `GET /api/admin/market/health` (посмотреть
сейчас) и ежедневная джоба `daily_market_health_report` (написать в лог, а при
проблемах — уровнем ERROR).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.database import async_session_maker

logger = logging.getLogger(__name__)


# Полный обход идёт в 02:00, инкрементальный в 14:00. 36 часов — это пропущенная
# ночь плюс запас: разово простить можно, двое суток молчания — уже поломка.
STALE_CRAWL_HOURS = 36

# Сколько дней «ни разу не пробованный» листинг может ждать очереди, прежде чем
# это считается застоем. Кулдаун повтора — 7 дней (_MATCH_RETRY_DAYS), так что
# новые позиции обязаны разбираться заметно быстрее него.
STALE_QUEUE_DAYS = 3

# Сколько записей без обложки при наличии магазинной картинки терпим. Ноль
# недостижим (плейсхолдеры магазинов отсекает фильтр мусора), но сотни означают,
# что харвест снова не работает.
MAX_HARVESTABLE_COVERS = 100


_STORE_SQL = text(
    """
    SELECT s.slug,
           s.is_active,
           s.last_successful_scrape_at,
           round(EXTRACT(EPOCH FROM (now() - s.last_successful_scrape_at)) / 3600.0, 1)
               AS hours_since_scrape,
           s.last_error,
           count(l.id)                                        AS listings,
           count(*) FILTER (WHERE l.status = 'in_stock')      AS in_stock,
           count(l.matched_record_id)                         AS matched,
           count(*) FILTER (WHERE l.matched_record_id IS NULL
                              AND l.match_attempted_at IS NULL
                              AND l.status IN ('in_stock', 'preorder'))
                                                              AS never_tried
    FROM stores s
    LEFT JOIN store_listings l ON l.store_id = s.id
    WHERE s.is_active
    GROUP BY s.slug, s.is_active, s.last_successful_scrape_at, s.last_error
    ORDER BY s.slug
    """
)

_QUEUE_SQL = text(
    """
    SELECT count(*)                                           AS total,
           count(*) FILTER (WHERE match_attempted_at IS NULL) AS never_tried,
           round(EXTRACT(EPOCH FROM (now() - min(first_seen_at)
               FILTER (WHERE match_attempted_at IS NULL))) / 86400.0, 1)
                                                              AS oldest_never_tried_days
    FROM store_listings
    WHERE matched_record_id IS NULL AND status IN ('in_stock', 'preorder')
    """
)

# Записи, которым обложку можно поставить бесплатно прямо сейчас: у листинга
# картинка есть, у записи — нет. Растёт → харвест сломан.
_COVERS_SQL = text(
    """
    SELECT count(DISTINCT r.id) AS harvestable
    FROM records r
    JOIN store_listings l ON l.matched_record_id = r.id
    WHERE r.discogs_id IS NOT NULL
      AND r.cover_image_url IS NULL
      AND r.cover_local_path IS NULL
      AND l.raw_payload->>'image_url' IS NOT NULL
    """
)


async def build_market_health_report() -> dict[str, Any]:
    """Считает сводку. Ничего не меняет — только читает."""
    async with async_session_maker() as db:
        stores = [dict(r) for r in (await db.execute(_STORE_SQL)).mappings().all()]
        queue = dict((await db.execute(_QUEUE_SQL)).mappings().one())
        covers = dict((await db.execute(_COVERS_SQL)).mappings().one())

    problems: list[str] = []

    for store in stores:
        store["matched_pct"] = (
            round(100.0 * store["matched"] / store["listings"], 1)
            if store["listings"] else None
        )
        hours = store["hours_since_scrape"]
        if hours is None:
            problems.append(f"{store['slug']}: ни одного успешного обхода")
        elif hours > STALE_CRAWL_HOURS:
            problems.append(
                f"{store['slug']}: последний успешный обход {hours:.0f} ч назад"
            )
        if store["last_error"]:
            problems.append(f"{store['slug']}: {store['last_error'][:120]}")

    oldest = queue.get("oldest_never_tried_days")
    if oldest is not None and oldest > STALE_QUEUE_DAYS:
        problems.append(
            f"очередь матчинга стоит: самый старый неразобранный листинг ждёт "
            f"{oldest:.0f} дн ({queue['never_tried']} не пробованы)"
        )

    if covers["harvestable"] > MAX_HARVESTABLE_COVERS:
        problems.append(
            f"обложки не осаждаются: {covers['harvestable']} записей без обложки "
            f"при наличии магазинной картинки"
        )

    return {
        "stores": stores,
        "match_queue": queue,
        "covers": covers,
        "problems": problems,
        "ok": not problems,
    }
