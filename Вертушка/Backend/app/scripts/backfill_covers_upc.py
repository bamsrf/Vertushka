"""Bulk-backfill обложек по ШТРИХКОДУ через Deezer — точный канал вместо угадывания.

Чем отличается от backfill_covers_deezer.py. Тот ищет по artist+title, то есть
угадывает: `Cause For Conflict` против `Cause for Conflict (Remastered)`,
`Kreator` против `Kreator (2)`. Полный обход 1.86 млн мастеров таким способом
дал 24%, и непокрытый остаток — ровно те, чьи названия не совпали. Здесь ключ
однозначный: UPC с конверта пластинки. Лейбл присваивает код изданию, а не
носителю, поэтому винил и цифра часто несут один и тот же штрихкод.

Почему этот канал стоило открыть (замеры на проде, 2026-08-17):

  канал            очередь        хит   темп      полный обход
  Deezer по UPC    2 305 208      15.3%  0.13 с    3.5 дня
  iTunes по имени  1 334 938      10.7%  3.1 с     49 дней

Разница в выхлопе за сутки обхода — 39×, и почти вся она из темпа, не из
хит-рейта. Пересечение с MB→CAA на выборке 150 — ноль: каналы дополняют друг
друга. Офлайн-каналы CAA к этому моменту исчерпаны (0 непроверенных MBID,
331 штрихкод из 2.3 млн в mb_barcode_covers), так что это следующий по
дешевизне источник.

Единица работы — УНИКАЛЬНЫЙ barcode_norm, а не релиз: у 91.6% штрихкодов ровно
один релиз, но один запрос закрывает все издания с этим кодом сразу.

Пишем URL в discogs_releases_index.cover_image_url (строки без обложки);
картинки материализуются лениво при просмотре (mirror-on-view).

Запуск на проде (фоном, переживает разрыв ssh):
  docker exec -d vertushka_api_blue sh -c \
    "python -m app.scripts.backfill_covers_upc > /app/uploads/backfill_upc.log 2>&1"

Тест на N штрихкодах: --max-requests 200
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time

from sqlalchemy import text

from app.database import async_session_maker
from app.services.deezer import DeezerQuotaExceeded, cover_by_upc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_upc")

WORKLIST = "cover_backfill_upc"
MARKER = "/app/uploads/.backfill_upc_enabled"

# Перекрытие сетевой латентности. Темп всё равно держит глобальный троттл
# Deezer (0.13 с), больше 4 воркеров смысла не имеют — только ждали бы лок.
_CONCURRENCY = 4

# Штрихкод, за которым висит больше этого числа релизов, — почти наверняка
# мусор в данных Discogs (общий код лейбла, «none»), а не реальное издание.
# Замер: таких всего 138 из 2.3 млн, худший держит 251 релиз. Пустить их —
# значит уехать одной обложкой на 251 разную пластинку.
_MAX_FANOUT = 20

# Бюджет стенных часов на один прогон scheduled-джобы. Не таймаут на партию:
# воркер проверяет дедлайн ПЕРЕД тем, как взять следующий штрихкод, поэтому
# незаданный вопрос физически не может попасть в done.
_RUN_BUDGET = 240

# Пауза при упоре в квоту Deezer. Прогон прерывается, недоспрошенные остаются
# в очереди — следующий запуск возьмёт их снова.
_QUOTA_BACKOFF = 60

# Сторож нулевого выхлопа: столько подряд промахов — и прогон прерывается с
# алертом. Защищает не от потери элементов (от неё защищает волна), а от
# СИСТЕМАТИЧЕСКИ НЕВЕРНОГО ЗАПРОСА, который выглядит как честный промах.
#
# Инцидент 18.08.2026: Deezer не нормализует ведущий ноль, обход шёл по
# возрастанию штрихкода и залип в блоках Universal (`06025x`), где работает
# только 12-значная форма. 1775 запросов подряд с нулём попаданий, три часа,
# все помечены пройденными — и ни одного сигнала.
#
# Порог выбран так, чтобы не ловить честно пустые блоки: при базовом хит-рейте
# 15% вероятность 500 промахов подряд неотличима от нуля, при пессимистичных
# 3% — порядка 1e-7. Ложное срабатывание стоит остановленного прогона, который
# человек перезапустит; пропущенный систематический баг стоит очереди.
_ZERO_STREAK_ABORT = 500


async def _ensure_infra() -> None:
    async with async_session_maker() as s:
        await s.execute(text(
            f"CREATE TABLE IF NOT EXISTS {WORKLIST} ("
            "  barcode_norm TEXT PRIMARY KEY,"
            "  done BOOLEAN NOT NULL DEFAULT FALSE)"
        ))
        await s.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{WORKLIST}_todo "
            f"ON {WORKLIST} (barcode_norm) WHERE NOT done"
        ))
        await s.commit()


async def _build_worklist(rebuild: bool = False) -> int:
    """Уникальные штрихкоды релизов без обложки. Идемпотентно."""
    async with async_session_maker() as s:
        await s.execute(text("SET statement_timeout = 900000"))
        if rebuild:
            await s.execute(text(f"TRUNCATE {WORKLIST}"))
            await s.commit()
        have = (await s.execute(text(f"SELECT count(*) FROM {WORKLIST}"))).scalar()
        if have and not rebuild:
            return int(have)

        logger.info("building UPC worklist (heavy agg over 13.1M rows, ~1-2 min)...")
        # Фильтр по форме кода делаем здесь, а не в Python: в barcode_norm дампа
        # лежат и каталожные номера, и мусор — тратить на них запросы незачем.
        await s.execute(text(
            f"INSERT INTO {WORKLIST} (barcode_norm) "
            "SELECT barcode_norm FROM discogs_releases_index "
            "WHERE cover_image_url IS NULL "
            "  AND barcode_norm ~ '^[0-9]{8,14}$' "
            "GROUP BY barcode_norm "
            f"HAVING count(*) <= {_MAX_FANOUT} "
            "ON CONFLICT (barcode_norm) DO NOTHING"
        ))
        await s.commit()
        total = (await s.execute(text(f"SELECT count(*) FROM {WORKLIST}"))).scalar()
        logger.info("UPC worklist: %d штрихкодов", total)
        return int(total)


async def _lookup_wave(barcodes: list[str], budget_s: float) -> tuple[list[tuple[str, str | None]], bool]:
    """Опросить штрихкоды. Возвращает (результаты опрошенных, упёрлись_в_квоту).

    Ключевое свойство: в результат попадает ТОЛЬКО то, что реально спросили.
    Дедлайн проверяется перед взятием следующего элемента из очереди, поэтому
    у незаданного вопроса не может появиться вердикт «обложки нет» — а именно
    так теряются элементы навсегда, ведь вызывающий метит их `done`.
    """
    queue: asyncio.Queue[str] = asyncio.Queue()
    for bc in barcodes:
        queue.put_nowait(bc)

    done: list[tuple[str, str | None]] = []
    deadline = time.monotonic() + budget_s
    quota_hit = asyncio.Event()

    async def worker() -> None:
        while not quota_hit.is_set() and time.monotonic() < deadline:
            try:
                bc = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                cover = await cover_by_upc(bc)
            except DeezerQuotaExceeded as e:
                logger.warning("Deezer quota: %s — прерываем волну, %s вернутся в очередь",
                               e, queue.qsize() + 1)
                quota_hit.set()
                return
            except Exception:
                logger.debug("upc lookup failed: %s", bc, exc_info=True)
                cover = None
            done.append((bc, cover.url if cover else None))

    await asyncio.gather(*(worker() for _ in range(_CONCURRENCY)))
    return done, quota_hit.is_set()


async def _persist(results: list[tuple[str, str | None]]) -> int:
    """Записать обложки и закрыть опрошенные штрихкоды. Возвращает число релизов."""
    hits = [(bc, url) for bc, url in results if url]
    touched = 0
    async with async_session_maker() as s:
        if hits:
            # По одному UPDATE на штрихкод: их в волне единицы, а условие
            # cover_image_url IS NULL обязано остаться — за время прогона строку
            # мог закрыть живой резолв или ночной перегрев.
            for bc, url in hits:
                res = await s.execute(text(
                    "UPDATE discogs_releases_index "
                    "SET cover_image_url = :u, cover_checked_at = now() "
                    "WHERE barcode_norm = :b AND cover_image_url IS NULL"
                ), {"u": url, "b": bc})
                touched += res.rowcount or 0
        await s.execute(text(
            f"UPDATE {WORKLIST} SET done = TRUE WHERE barcode_norm = ANY(:ids)"
        ), {"ids": [bc for bc, _ in results]})
        await s.commit()
    return touched


async def run(batch: int = 200, max_requests: int | None = None,
              budget_s: float = _RUN_BUDGET) -> dict:
    """Один проход: волнами по batch штрихкодов, пока не выйдет бюджет."""
    stats = {"asked": 0, "hits": 0, "releases": 0, "quota": False, "zero_streak": False}
    started = time.monotonic()
    streak = 0  # промахов подряд, через границы волн

    if not await _build_worklist():
        logger.info("UPC worklist пуст — нечего делать")
        return stats

    while True:
        left = budget_s - (time.monotonic() - started)
        if left <= 1:
            break
        if max_requests is not None and stats["asked"] >= max_requests:
            break

        async with async_session_maker() as s:
            rows = (await s.execute(text(
                f"SELECT barcode_norm FROM {WORKLIST} WHERE NOT done "
                "ORDER BY barcode_norm LIMIT :b"
            ), {"b": batch})).scalars().all()
        if not rows:
            logger.info("очередь пройдена целиком")
            break

        results, quota = await _lookup_wave(list(rows), left)
        if results:
            stats["releases"] += await _persist(results)
            stats["asked"] += len(results)
            stats["hits"] += sum(1 for _, url in results if url)
        # Считаем серию по порядку внутри волны: важна именно длина цепочки
        # промахов, а не их доля.
        for _, url in results:
            streak = 0 if url else streak + 1
        if streak >= _ZERO_STREAK_ABORT:
            stats["zero_streak"] = True
            logger.error(
                "upc: %d промахов подряд — прерываем прогон. Похоже на "
                "систематически неверную форму запроса, а не на пустой блок; "
                "последний штрихкод %s", streak, results[-1][0] if results else "?",
            )
            from app.services import alerts
            alerts.fire_and_forget(
                key="cover_upc_zero_yield",
                title=f"UPC-обход: {streak} промахов подряд",
                body=(
                    f"Прогон остановлен. Обработано {stats['asked']} за прогон, "
                    f"попаданий {stats['hits']}. Проверить форму запроса к Deezer "
                    f"на штрихкодах около {results[-1][0] if results else '?'} — "
                    f"так выглядел баг с ведущим нулём."
                ),
            )
            break
        if quota:
            stats["quota"] = True
            break
        if not results:
            # Ни одного ответа за всю волну — сеть/сервис лежат. Продолжать
            # нельзя: done не проставится, следующий SELECT вернёт те же строки.
            logger.error("волна без единого ответа — прерываем проход")
            break

        logger.info("upc: asked=%d hits=%d (%.1f%%) releases=%d",
                    stats["asked"], stats["hits"],
                    100 * stats["hits"] / max(stats["asked"], 1), stats["releases"])

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    return stats


async def run_scheduled_batch() -> None:
    """Гейт-маркер + ограниченный проход для APScheduler-джобы."""
    if not os.path.exists(MARKER):
        return
    await _ensure_infra()
    stats = await run()
    if stats.get("quota"):
        await asyncio.sleep(_QUOTA_BACKOFF)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--max-requests", type=int, default=None,
                    help="Остановиться после N опросов (для теста)")
    ap.add_argument("--budget", type=float, default=3600.0,
                    help="Бюджет стенных часов на прогон, с")
    ap.add_argument("--rebuild-worklist", action="store_true")
    args = ap.parse_args()

    await _ensure_infra()
    if args.rebuild_worklist:
        await _build_worklist(rebuild=True)
    stats = await run(args.batch, args.max_requests, args.budget)
    logger.info("готово: %s", stats)


if __name__ == "__main__":
    asyncio.run(main())
