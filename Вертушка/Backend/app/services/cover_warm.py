"""Фоновый прогрев обложек для строк dump-индекса (discogs_releases_index).

Дамп Discogs не несёт image URLs — поисковая выдача из дампа без обложек,
пока релиз не откроют (enrichment). Этот сервис греет обложки для топ-результатов
поиска fire-and-forget задачей:

  1. Cover Art Archive по barcode_norm — бесплатно, мимо Discogs rate-limit.
  2. Discogs /releases/{id} (Priority.ENRICHMENT, 1 вызов без фан-аута) —
     капится _DISCOGS_BUDGET_PER_BATCH, чтобы всплеск поисков не съел бюджет.

Найденный URL пишется прямо в discogs_releases_index.cover_image_url —
его подхватывают и поисковая выдача (_search_local_index COALESCE), и
detail-stub (records.py). Один прогрев улучшает все будущие выдачи.

Дедупликация: Redis SET NX `cover_warm:{discogs_id}` на 6 часов — релиз,
по которому уже ходили (включая неудачи), не дёргается повторно.
"""
import asyncio
import logging

from sqlalchemy import text

from app.database import async_session_maker
from app.services.cache import cache

logger = logging.getLogger(__name__)

_WARM_LOCK_TTL = 6 * 3600
# Сколько Discogs-вызовов позволяем одному warm-батчу (CAA не лимитируем —
# он бесплатный и сам троттлится 1 rps в cover_fallback).
_DISCOGS_BUDGET_PER_BATCH = 3
# Глобальный кап параллельных warm-батчей на процесс — защита от лавины
# create_task при всплеске поисков.
_warm_semaphore = asyncio.Semaphore(4)


async def warm_dump_covers(discogs_ids: list[str]) -> None:
    """Прогреть обложки для dump-строк без cover_image_url.

    Вызывается fire-and-forget из /records/search. Своя DB-сессия,
    все ошибки глотаются — UX поиска не зависит от прогрева.
    """
    if not discogs_ids:
        return
    try:
        async with _warm_semaphore:
            await _warm_batch(discogs_ids)
    except Exception:
        logger.exception("cover warm batch failed")


async def _warm_batch(discogs_ids: list[str]) -> None:
    from app.services.cover_fallback import cover_url_by_barcode
    from app.services.discogs import DiscogsService

    # Дедуп через Redis: берём в работу только те id, что никто не греет
    # и не грел последние 6 часов.
    to_warm: list[str] = []
    for did in discogs_ids:
        if await cache.set_nx("cover_warm", did, 1, ttl=_WARM_LOCK_TTL):
            to_warm.append(did)
    if not to_warm:
        return

    discogs = DiscogsService()
    discogs_budget = _DISCOGS_BUDGET_PER_BATCH

    async with async_session_maker() as session:
        ids = [int(d) for d in to_warm if d.isdigit()]
        if not ids:
            return
        rows = (await session.execute(
            text(
                "SELECT discogs_id::text AS discogs_id, barcode_norm "
                "FROM discogs_releases_index "
                "WHERE discogs_id = ANY(:ids) "
                "AND cover_image_url IS NULL"
            ),
            {"ids": ids},
        )).mappings().all()

        warmed = 0
        for row in rows:
            did = row["discogs_id"]
            cover: str | None = None

            # 1) CAA по barcode — бесплатно
            if row["barcode_norm"]:
                cover = await cover_url_by_barcode(row["barcode_norm"])

            # 2) Discogs — низкий приоритет, в рамках бюджета батча
            if not cover and discogs_budget > 0:
                discogs_budget -= 1
                cover = await discogs.get_release_cover(did)

            if not cover:
                continue

            await session.execute(
                text(
                    "UPDATE discogs_releases_index "
                    "SET cover_image_url = :url "
                    "WHERE discogs_id = :did "
                    "AND cover_image_url IS NULL"
                ),
                {"url": cover, "did": int(did)},
            )
            warmed += 1

        if warmed:
            await session.commit()
            logger.info("cover warm: %d/%d covers written", warmed, len(rows))


def schedule_warm_dump_covers(discogs_ids: list[str]) -> None:
    """fire-and-forget обёртка для вызова из request handler'а."""
    if not discogs_ids:
        return
    task = asyncio.create_task(warm_dump_covers(discogs_ids))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
