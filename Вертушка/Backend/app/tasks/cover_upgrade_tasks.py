"""Ночной перегрев мелких мастеров обложек — доводит фикс тира до глаз юзера.

Зачем отдельная задача. Гейт тира (cover_quality) остановил появление НОВЫХ
мелких мастеров, а heal-скрипт промерил существующие: на 2026-08-13 их оказалось
13 124 из 24 404 (54%). Но перезаписать их само собой ничто не могло:

- `ensure_cover_cached` возвращается сразу, если файл на диске есть — а у них он
  есть, просто мелкий. Плюс зовётся только при добавлении в коллекцию/вишлист.
- `drip_covers_batch` берёт строки дампа, где `cover_image_url IS NULL` — то
  есть вообще без обложки.
- `backfill_store_covers` берёт записи, где `cover_local_path IS NULL` — без файла.

То есть апгрейд-ветка в `download_and_store` была недостижима. Эта задача —
единственный, кто её вызывает.

Discogs НЕ трогаем вообще (`discogs_probe=None`): вся мотивация перегрева — уйти
от их API, и их же 150px-thumb сюда и привёл. Работают только бесплатные
источники: CAA по офлайн-маппингу → CAA по barcode → Deezer cover_xl → iTunes.

Два ограничителя вместо одного: `limit` по числу записей И `max_seconds` по
стенным часам. Второй нужен потому, что латентность источников не наша —
iTunes троттлится 3.1с на запрос, и партия «неудачников», дошедших до пятой
ступени, растянула бы прогон непредсказуемо.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.services.cache import cache
from app.services.cover_demand import TRIGGER_SWEEP
from app.services.cover_quality import MASTER_MIN_SIDE, is_thumb_grade

logger = logging.getLogger(__name__)

# Кулдаун на попытку апгрейда. Релиз, для которого бесплатная лестница ничего не
# нашла, не должен опрашиваться каждую ночь: источники не меняются так быстро.
# Успешный апгрейд поднимает cover_min_side выше порога, и запись уходит из
# выборки сама — кулдаун ей уже не нужен.
_ATTEMPT_TTL = 30 * 86400
_ATTEMPT_NS = "cover_upgrade"

# Сколько кандидатов вытаскиваем из БД на один проход: с запасом к лимиту,
# потому что часть отсеется кулдауном уже в Python (Redis в SQL не заджойнить).
_FETCH_MULTIPLIER = 3


async def upgrade_low_res_covers(
    limit: int | None = None,
    max_seconds: int | None = None,
) -> dict:
    """Перегреть партию мелких мастеров. Возвращает счётчики для логов/тестов.

    Ошибки отдельных релизов не роняют проход: у одного может лежать битый
    источник, остальные обязаны догреться.
    """
    settings = get_settings()
    if not settings.cover_upgrade_enabled:
        return {"skipped": "disabled"}

    limit = limit or settings.cover_upgrade_batch
    max_seconds = max_seconds or settings.cover_upgrade_max_seconds
    started = time.monotonic()

    from app.services.cover_storage import CoverStorageService
    from app.services.cover_warm import resolve_cover_url

    service = CoverStorageService()
    stats = {"considered": 0, "attempted": 0, "upgraded": 0, "no_source": 0, "still_small": 0}

    async with async_session_maker() as session:
        # ДВА запроса, а не JOIN. Соблазнительный
        # `LEFT JOIN discogs_releases_index d ON d.discogs_id::text = r.discogs_id`
        # даёт statement timeout: каст левой части выключает индекс по primary key,
        # и Postgres идёт полным проходом по 13.1 млн строк дампа. Проверено на
        # проде — первый запуск упал именно так.
        #
        # Худшие первыми: 150px раздражает сильнее, чем 400px. `records` — 34k
        # строк / 51 МБ, seq scan по ним стоит копейки, индекс не нужен.
        # Фильтр по цифрам — у store-native записей id вида 'store:...'.
        cand = (
            await session.execute(
                text(
                    """
                    SELECT discogs_id, title, artist, cover_min_side
                    FROM records
                    WHERE cover_local_path IS NOT NULL
                      AND cover_min_side IS NOT NULL
                      AND cover_min_side < :thr
                      AND discogs_id ~ '^[0-9]+$'
                      AND merged_into_id IS NULL
                    ORDER BY cover_min_side ASC
                    LIMIT :lim
                    """
                ),
                {"thr": MASTER_MIN_SIDE, "lim": limit * _FETCH_MULTIPLIER},
            )
        ).mappings().all()

        # Метаданные для 2-5 ступеней лестницы — одним индексным запросом по
        # bigint-массиву (так же, как _covers_from_index в records.py).
        meta: dict[str, dict] = {}
        if cand:
            meta_rows = (
                await session.execute(
                    text(
                        "SELECT discogs_id::text AS did, barcode_norm, year, label "
                        "FROM discogs_releases_index WHERE discogs_id = ANY(:ids)"
                    ),
                    {"ids": [int(c["discogs_id"]) for c in cand]},
                )
            ).mappings().all()
            meta = {m["did"]: dict(m) for m in meta_rows}

        rows = [{**dict(c), **meta.get(c["discogs_id"], {})} for c in cand]

        for row in rows:
            stats["considered"] += 1
            if stats["attempted"] >= limit:
                break
            if time.monotonic() - started > max_seconds:
                logger.info("cover upgrade: wall-clock budget %ds exhausted", max_seconds)
                break

            did = row["discogs_id"]
            # Кулдаун: set_nx вернёт False, если попытка была недавно.
            if not await cache.set_nx(_ATTEMPT_NS, did, 1, ttl=_ATTEMPT_TTL):
                continue

            stats["attempted"] += 1
            try:
                cover = await resolve_cover_url(session, row, discogs_probe=None)
            except Exception:
                logger.debug("cover upgrade: resolve failed for %s", did, exc_info=True)
                cover = None

            if not cover:
                stats["no_source"] += 1
                continue

            # Мелкий источник смысла не имеет — download_and_store его и так
            # отвергнет, но проверить здесь дешевле, чем ходить по сети.
            if is_thumb_grade(cover):
                stats["no_source"] += 1
                continue

            try:
                await service.download_and_store(
                    did, cover, session, trigger=TRIGGER_SWEEP,
                )
            except Exception:
                logger.debug("cover upgrade: download failed for %s", did, exc_info=True)
                continue

            # Проверяем, что стало лучше: источник мог отдать 400px, и тогда
            # запись останется в выборке — но уже под кулдауном, без спама.
            new_side = (
                await session.execute(
                    text("SELECT cover_min_side FROM records WHERE discogs_id = :did"),
                    {"did": did},
                )
            ).scalars().first()
            if new_side is not None and new_side >= MASTER_MIN_SIDE:
                stats["upgraded"] += 1
            else:
                stats["still_small"] += 1

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    logger.info(
        "cover upgrade: attempted %d, upgraded %d, no source %d, still small %d (%.0fs)",
        stats["attempted"], stats["upgraded"], stats["no_source"],
        stats["still_small"], stats["elapsed_s"],
    )
    return stats
