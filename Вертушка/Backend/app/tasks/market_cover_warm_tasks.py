"""Прогрев обложек живой витрины Маркета из БЕСПЛАТНЫХ источников.

Зачем. Замер 15.09.2026 по витрине (записи с in_stock-листингом за 7 дней):

    всего                       45 241
    уже зеркалировано           32 262  (71%)
    есть бесплатный адрес        8 405  (19%)  ← этим и занимается задача
    только картинка Discogs      4 482  (10%)
    адреса нет вовсе                92

При этом каждый третий запрос обложки в проде отдаёт 404: у записи нет зеркала,
единственный источник — Discogs, а дневной бюджет его картинок (800/сутки на
IP, см. discogs_img_daily_budget) выбран. Пользователь видит серую плитку, а
клиент раз за разом просит одно и то же — одна обложка ловила по 21 промаху за
два часа.

Ключевое: 19% пустот закрываются вообще без квоты Discogs — адрес уже известен
и ведёт на CAA, Deezer, iTunes или в сам магазин. Скачать их мешало только то,
что никто не ходил.

Порядок — по спросу, а не по свежести каталога: витрина Маркета это то, что
люди видят первым экраном. Зеркалирование мастеров (master_mirror_tasks)
работает вширь по каталогу, эта задача — вглубь по тому, что показывается.

ЧЕГО ЗАДАЧА НЕ ДЕЛАЕТ. Не подставляет обложку МАСТЕРА вместо обложки пресса,
даже когда мастер-обложка бесплатна, а своя — платная (таких 2 138). Это
сознательное продуктовое решение: мастер-обложка обслуживает сетку артиста,
а экран версий — нет (COVERS_STRATEGY.md), и подмена релиза чужим прессом уже
приводила к инциденту 12.09.2026. Бесплатную альтернативу берём только
release-точную: CAA по офлайн-маппингу mb_discogs_map (discogs_id ↔ MBID).
"""
import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker

logger = logging.getLogger(__name__)

_MAX_RUN_SECONDS = 100

# Записи витрины без зеркала, чей СОБСТВЕННЫЙ адрес обложки бесплатный.
# i.discogs.com отсекаем по хосту, а не по колонке source: колонка описывает
# того, кто нашёл строку, а не того, чья в ней картинка (см. master_mirror).
_FREE_URL_SQL = """
SELECT r.discogs_id, r.cover_image_url
FROM store_listings sl
JOIN records r ON r.id = sl.matched_record_id
WHERE sl.status = 'in_stock'
  AND sl.last_seen_at > now() - interval '7 days'
  AND r.cover_cached_at IS NULL
  AND r.cover_image_url IS NOT NULL
  AND r.cover_image_url NOT LIKE '%i.discogs.com%'
  AND r.discogs_id IS NOT NULL
GROUP BY r.discogs_id, r.cover_image_url
ORDER BY max(sl.last_seen_at) DESC
LIMIT :n
"""

# Записи витрины, у которых свой адрес платный, но есть release-точная
# бесплатная обложка в Cover Art Archive. CAA без rate-limit вовсе.
_CAA_CANDIDATES_SQL = """
SELECT r.discogs_id
FROM store_listings sl
JOIN records r ON r.id = sl.matched_record_id
JOIN mb_discogs_map m ON m.discogs_id = r.discogs_id::bigint
WHERE sl.status = 'in_stock'
  AND sl.last_seen_at > now() - interval '7 days'
  AND r.cover_cached_at IS NULL
  AND r.discogs_id ~ '^[0-9]+$'
  AND m.has_front
  AND (r.cover_image_url IS NULL OR r.cover_image_url LIKE '%i.discogs.com%')
GROUP BY r.discogs_id
ORDER BY max(sl.last_seen_at) DESC
LIMIT :n
"""


async def warm_market_covers_batch() -> dict:
    """Один прогон. Сначала свои бесплатные адреса, потом CAA-замены."""
    settings = get_settings()
    if not settings.market_warm_enabled:
        return {"skipped": "disabled"}

    from app.services.cover_storage import CoverStorageService
    from app.services.cover_demand import TRIGGER_BACKFILL

    service = CoverStorageService()
    started = time.monotonic()
    done = failed = swapped = 0
    batch = settings.market_warm_batch
    pace = settings.market_warm_pace_sec

    async with async_session_maker() as db:
        rows = (await db.execute(text(_FREE_URL_SQL), {"n": batch})).all()

        for i, (discogs_id, url) in enumerate(rows):
            if time.monotonic() - started > _MAX_RUN_SECONDS:
                break
            if i:
                await asyncio.sleep(pace)
            try:
                stored = await service.download_and_store(
                    discogs_id, url, db, trigger=TRIGGER_BACKFILL,
                )
            except Exception:
                logger.warning("market warm: %s упал", discogs_id, exc_info=True)
                stored = None
            done += 1 if stored else 0
            failed += 0 if stored else 1

        # Вторым заходом — CAA-замены платного адреса на бесплатный. Отдельный
        # бюджет: даже если первая очередь пуста, замены идти должны.
        if time.monotonic() - started <= _MAX_RUN_SECONDS:
            swapped = await _swap_to_caa(db, service, settings.market_warm_caa_batch, started, pace)

    if done or failed or swapped:
        logger.info(
            "market warm: %d обложек зеркалировано, %d не вышло, "
            "%d переведено на CAA",
            done, failed, swapped,
        )
    return {"done": done, "failed": failed, "swapped": swapped}


async def _swap_to_caa(db, service, limit: int, started: float, pace: float) -> int:
    """Платный адрес → бесплатный CAA, если он есть в офлайн-маппинге.

    Пишем найденный URL в records.cover_image_url: иначе при следующей эвикции
    мост снова пошёл бы за платной картинкой, и экономия была бы разовой.
    """
    from app.services.cover_fallback import cover_url_by_discogs_id
    from app.services.cover_demand import TRIGGER_BACKFILL

    rows = (await db.execute(text(_CAA_CANDIDATES_SQL), {"n": limit})).scalars().all()
    swapped = 0
    for i, discogs_id in enumerate(rows):
        if time.monotonic() - started > _MAX_RUN_SECONDS:
            break
        if i:
            await asyncio.sleep(pace)
        try:
            caa_url = await cover_url_by_discogs_id(db, discogs_id)
        except Exception:
            logger.debug("market warm: CAA-резолв %s упал", discogs_id, exc_info=True)
            continue
        if not caa_url:
            continue
        stored = await service.download_and_store(
            discogs_id, caa_url, db, trigger=TRIGGER_BACKFILL,
        )
        if not stored:
            continue
        await db.execute(
            text(
                "UPDATE records SET cover_image_url = :url "
                "WHERE discogs_id = :did"
            ),
            {"url": caa_url, "did": discogs_id},
        )
        await db.commit()
        swapped += 1
    return swapped
