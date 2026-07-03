"""Drip-воркер обложек: скармливает простаивающие токены app-bucket'а
Discogs API для прогрева обложек dump-строк без cover_image_url.

Математика: 60 req/min × 24ч = ~86K обложек/день одним app-токеном — если
bucket простаивает. Воркер запускается раз в минуту (APScheduler, scheduler-
контейнер) и работает ТОЛЬКО при почти полном bucket'е:

  peek_tokens() > _HEADROOM → тратим (tokens - _HEADROOM), максимум _MAX_PER_RUN

Юзерский трафик всегда в приоритете: между каждым запросом peek повторяется,
при падении ниже headroom — немедленный выход. Redis недоступен → пропуск
(без Redis bucket не общий, рисковать нельзя).

Порядок кандидатов: year DESC — свежий каталог греется первым (совпадает с
витриной новинок и живым спросом). Строки, которые ещё ждёт CAA bulk-warm
(mb_discogs_map.caa_checked_at IS NULL), пропускаются — их закроет бесплатный
источник, Discogs-токены на них не тратим.

cover_checked_at ставится после КАЖДОЙ попытки (включая «у релиза нет
обложки») — строка навсегда уходит из очереди. Ложные промахи из-за сетевых
ошибок возможны, но редки (headroom-гейт исключает 429); при желании
перепроверить: UPDATE ... SET cover_checked_at = NULL.
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.services.cache import cache

logger = logging.getLogger(__name__)

# Bucket app-лимитера (rate_limiter.py: capacity=55, refill=0.95/s).
_BUCKET_KEY = "app"
_BUCKET_CAPACITY = 55
_BUCKET_REFILL = 0.95
# Ниже этого уровня токены не трогаем — резерв для живых юзеров.
_HEADROOM = 35
# Кап на один прогон (прогоны каждую минуту). Вместе с паузой _PACE_SEC
# даёт размазанные ~10 req/min вместо burst'а: Discogs считает скользящее
# окно 60/min, а наш bucket в worst case пропускал burst 55 + рефилл —
# drip-насыщение превращало это в постоянные 429 (2026-07-03).
_MAX_PER_RUN = 10
_PACE_SEC = 2.0


async def drip_covers_batch() -> None:
    """Один прогон drip'а. Вызывается APScheduler'ом каждую минуту."""
    if not get_settings().cover_drip_enabled:
        return

    # Discogs недавно отвечал 429 app-токену (флаг ставит DiscogsService._get
    # из любого контейнера) — уступаем окно юзерам, молчим до истечения TTL.
    if await cache.get("discogs", "app_429"):
        return

    tokens = await cache.peek_tokens(_BUCKET_KEY, _BUCKET_CAPACITY, _BUCKET_REFILL)
    if tokens is None or tokens <= _HEADROOM:
        return
    budget = min(int(tokens - _HEADROOM), _MAX_PER_RUN)
    if budget <= 0:
        return

    from app.services.discogs import DiscogsService
    discogs = DiscogsService()

    async with async_session_maker() as session:
        rows = (await session.execute(
            text(
                "SELECT d.discogs_id::text AS discogs_id "
                "FROM discogs_releases_index d "
                "WHERE d.cover_image_url IS NULL "
                "AND d.cover_checked_at IS NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM mb_discogs_map m "
                "  WHERE m.discogs_id = d.discogs_id "
                "  AND m.caa_checked_at IS NULL"
                ") "
                "ORDER BY d.year DESC NULLS LAST "
                "LIMIT :n"
            ),
            {"n": budget},
        )).scalars().all()

        if not rows:
            return

        warmed = 0
        checked = 0
        for i, did in enumerate(rows):
            # Пауза между запросами — размазываем нагрузку вместо burst'а.
            if i:
                await asyncio.sleep(_PACE_SEC)
            # Re-peek перед каждым запросом: юзерский всплеск или свежий 429 —
            # выходим немедленно.
            tokens = await cache.peek_tokens(_BUCKET_KEY, _BUCKET_CAPACITY, _BUCKET_REFILL)
            if tokens is None or tokens <= _HEADROOM or await cache.get("discogs", "app_429"):
                break

            cover = await discogs.get_release_cover(did)
            checked += 1
            if cover:
                warmed += 1
            await session.execute(
                text(
                    "UPDATE discogs_releases_index "
                    "SET cover_image_url = COALESCE(cover_image_url, :url), "
                    "    cover_checked_at = :now "
                    "WHERE discogs_id = :did"
                ),
                {"url": cover, "did": int(did), "now": datetime.utcnow()},
            )

        if checked:
            await session.commit()
            logger.info("cover drip: %d checked, %d covers found", checked, warmed)
