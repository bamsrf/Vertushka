"""Обогащение существующих записей вне Discogs (source='store') из Yandex Music.

Идея: store-native записи созданы из данных листинга магазина — часто без
настоящей обложки альбома, года и треклиста. Yandex закрывает именно русский/
советский слой, которого нет в Discogs. Джоба батчами добирает
yandex_album_id + обложку/год/треклист для записей, где их ещё нет.

Гейт — тот же флаг, что у матчинга: YANDEX_MATCH_ENABLED (включаешь Yandex —
работают и новый матчинг, и добор старых). Троттл держит сам сервис (~4 req/s).
Резюмируемо: обработанные получают yandex_album_id и выпадают из выборки.
"""
import logging

from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.models.record import Record
from app.services.yandex_music import album_by_meta

logger = logging.getLogger(__name__)

# Кап на прогон: держим короткие батчи (в scheduler-контейнере, max_instances=1).
_MAX_PER_RUN = 40


async def enrich_store_native_yandex() -> None:
    if not get_settings().yandex_match_enabled:
        return

    async with async_session_maker() as db:
        rows = (await db.execute(text(
            "SELECT id, artist, title, year FROM records "
            "WHERE source = 'store' AND yandex_album_id IS NULL "
            "AND merged_into_id IS NULL AND artist IS NOT NULL AND title IS NOT NULL "
            "ORDER BY created_at DESC LIMIT :lim"
        ), {"lim": _MAX_PER_RUN})).mappings().all()

    if not rows:
        return

    enriched = 0
    for r in rows:
        try:
            album = await album_by_meta(r["artist"], r["title"], r["year"])
        except Exception:
            logger.debug("yandex enrich lookup failed for %s", r["id"], exc_info=True)
            album = None

        async with async_session_maker() as db:
            rec = await db.get(Record, r["id"])
            if rec is None or rec.yandex_album_id:
                continue
            if not album:
                # Промах фиксируем пустым маркером, чтобы не дёргать Yandex каждый
                # прогон по одной и той же записи (снимается: SET yandex_album_id=NULL).
                rec.yandex_album_id = ""
                await db.commit()
                continue

            rec.yandex_album_id = str(album.album_id)
            rec.yandex_data = {
                "album_id": album.album_id,
                "cover_image_url": album.url,
                "year": album.year,
                "genre": album.genre,
                "tracklist": album.tracklist,
            }
            if album.url and not rec.cover_image_url:
                rec.cover_image_url = album.url
                from app.services.cover_storage import schedule_store_native_cover_cache
                schedule_store_native_cover_cache(rec.id, album.url)
            if album.year and not rec.year:
                rec.year = album.year
            if album.tracklist and not rec.tracklist:
                rec.tracklist = album.tracklist
            await db.commit()
            enriched += 1

    logger.info("yandex enrich: seen=%d enriched=%d", len(rows), enriched)
