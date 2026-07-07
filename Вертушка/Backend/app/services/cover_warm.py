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

# Сильные ссылки на fire-and-forget warm-задачи — asyncio держит только weak
# reference, local task-var уходит из скоупа сразу и GC может собрать warm до
# завершения. Модульный set удерживает до done-callback.
_warm_tasks: set[asyncio.Task] = set()


def _retain_warm(coro) -> None:
    task = asyncio.create_task(coro)
    _warm_tasks.add(task)
    task.add_done_callback(_warm_tasks.discard)

_WARM_LOCK_TTL = 6 * 3600
# Сколько Discogs-вызовов позволяем одному warm-батчу (CAA не лимитируем —
# он бесплатный и сам троттлится 1 rps в cover_fallback).
_DISCOGS_BUDGET_PER_BATCH = 3
# Глобальный кап параллельных warm-батчей на процесс — защита от лавины
# create_task при всплеске поисков.
_warm_semaphore = asyncio.Semaphore(4)


async def warm_dump_covers(discogs_ids: list[str], discogs_budget: int | None = None) -> None:
    """Прогреть обложки для dump-строк без cover_image_url.

    Вызывается fire-and-forget из /records/search. Своя DB-сессия,
    все ошибки глотаются — UX поиска не зависит от прогрева.
    """
    if not discogs_ids:
        return
    try:
        async with _warm_semaphore:
            await _warm_batch(discogs_ids, discogs_budget)
    except Exception:
        logger.exception("cover warm batch failed")


async def _warm_batch(discogs_ids: list[str], budget_override: int | None = None) -> None:
    from app.services.cover_fallback import (
        cover_url_by_artist_title,
        cover_url_by_barcode,
        cover_url_by_discogs_id,
    )
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
    discogs_budget = budget_override if budget_override is not None else _DISCOGS_BUDGET_PER_BATCH

    async with async_session_maker() as session:
        ids = [int(d) for d in to_warm if d.isdigit()]
        if not ids:
            return
        rows = (await session.execute(
            text(
                "SELECT discogs_id::text AS discogs_id, barcode_norm, artist, title, "
                "year, label "
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

            # 1) CAA по офлайн mb_discogs_map — 1 HEAD, без MB-троттла
            cover = await cover_url_by_discogs_id(session, did)

            # 2) CAA по barcode — бесплатно, но с MB-троттлом 1 rps
            if not cover and row["barcode_norm"]:
                cover = await cover_url_by_barcode(row["barcode_norm"])

            # 3) Deezer — бесплатно, cover_xl 1000+, стабильный публичный URL.
            #    До Discogs: экономит бюджет и не протухает (i.discogs.com — да).
            if not cover:
                from app.services.deezer import cover_by_meta
                dz = await cover_by_meta(
                    row["artist"], row["title"], year=row.get("year"),
                    label=row.get("label"),
                )
                if dz:
                    cover = dz.url

            # 4) Discogs — низкий приоритет, в рамках бюджета батча
            if not cover and discogs_budget > 0:
                discogs_budget -= 1
                cover = await discogs.get_release_cover(did)

            # 5) iTunes — album-level artwork, последний шанс
            if not cover:
                cover = await cover_url_by_artist_title(row["artist"], row["title"])

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


def schedule_warm_dump_covers(discogs_ids: list[str], discogs_budget: int | None = None) -> None:
    """fire-and-forget обёртка для вызова из request handler'а."""
    if not discogs_ids:
        return
    _retain_warm(warm_dump_covers(discogs_ids, discogs_budget))


async def warm_artist_master_covers(artist_id: str, artist_name: str) -> None:
    """Batch-прогрев обложек ВСЕХ мастеров артиста: 1-3 вызова Search API
    (до 300 мастеров) → discogs_master_covers. Убивает заглушки первого
    просмотра: сетка артиста подхватит через COALESCE на клиентском retry
    через секунды, и навсегда для всех последующих юзеров.

    ON CONFLICT DO NOTHING — live get_master пишет более каноничную обложку,
    её не перетираем. NX-лок 6ч — один прогрев на артиста, не на страницу.
    """
    if not await cache.set_nx("artist_cover_warm", artist_id, 1, ttl=6 * 3600):
        return
    try:
        from app.services.discogs import DiscogsService

        # max_pages=5: у крупных артистов (Elton John — 448 мастеров) топ-300
        # Search не покрывал хвост синглов, и их карточки оставались пустыми.
        cover_map = await DiscogsService()._artist_master_cover_map(
            artist_id, artist_name, max_pages=5,
        )
        rows = [
            (int(mid), c["cover_image"])
            for mid, c in cover_map.items()
            if mid.isdigit() and c.get("cover_image")
            and "api-img.discogs.com" not in c["cover_image"]
            # st.discogs.com/.../spacer.gif — no-image заглушка Discogs, не обложка.
            and "spacer.gif" not in c["cover_image"]
            and "st.discogs.com" not in c["cover_image"]
        ]
        if not rows:
            return
        async with async_session_maker() as session:
            await session.execute(
                text(
                    "INSERT INTO discogs_master_covers (master_id, cover_image_url) "
                    "SELECT unnest(CAST(:ids AS bigint[])), unnest(CAST(:urls AS text[])) "
                    "ON CONFLICT (master_id) DO NOTHING"
                ),
                {"ids": [r[0] for r in rows], "urls": [r[1] for r in rows]},
            )
            await session.commit()
        logger.info("artist cover warm: %s — %d master covers", artist_id, len(rows))
    except Exception:
        logger.exception("artist cover warm failed: %s", artist_id)


def schedule_warm_artist_master_covers(artist_id: str, artist_name: str) -> None:
    """fire-and-forget обёртка."""
    _retain_warm(warm_artist_master_covers(artist_id, artist_name))
