"""Обобщённый bulk-backfill обложек хвоста через дополнительные источники.

Дополняет Deezer-воркер (backfill_covers_deezer.py) вторыми каталогами:
- `itunes`  — рабочая лошадь по объёму: западный латинский хвост, которого
              Deezer не нашёл. Троттл ~19 req/min (iTunes Search API).
- `yandex`  — русский/советский + транслит-СССР слой, которого структурно нет
              ни в Discogs, ни в Deezer/iTunes. Демонстрирует лучший hit-rate
              именно по кириллице (в живых данных ~10-12%).

Порядок в жизни: Deezer снимает «лёгкую» вершину master'ов → остаток (не попал
в discogs_master_covers) добираем iTunes, затем Yandex. Каждый источник ведёт
СВОЮ worklist-таблицу `cover_backfill_masters_{source}` и checkpoint
`kind='masters_{source}'`, поэтому прогоны независимы и не мешают Deezer.
Worklist строится анти-джойном к discogs_master_covers → в него попадают ТОЛЬКО
мастера, которых предыдущие источники ещё не закрыли.

Пишем ТОЛЬКО URL в discogs_master_covers (source=itunes|yandex); картинки
материализуются лениво при просмотре (mirror-on-view).

Resumable (done-флаги), rate-limit держится глобальным троттлом внутри сервиса.

Запуск на проде (фоном, переживает разрыв ssh):
  docker compose -f docker-compose.prod.yml exec -T -d api \
    python -m app.scripts.backfill_covers --source yandex --kind masters \
    >/app/uploads/backfill_covers_yandex.log 2>&1

Тест на N матчах: --max-requests 200
"""
import argparse
import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import text

from app.database import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("backfill_covers")


# ── Провайдеры ───────────────────────────────────────────────────────────
# lookup: (artist, title, year) -> URL|None. Нормализация/троттл — внутри сервиса.
async def _itunes_lookup(artist: str, title: str, year: int | None) -> str | None:
    from app.services.cover_fallback import cover_url_by_artist_title
    return await cover_url_by_artist_title(artist, title)


async def _yandex_lookup(artist: str, title: str, year: int | None) -> str | None:
    from app.services.yandex_music import cover_by_meta
    yc = await cover_by_meta(artist, title, year=year)
    return yc.url if yc else None


@dataclass
class Provider:
    name: str
    lookup: Callable[[str, str, int | None], Awaitable[str | None]]
    concurrency: int  # перекрытие сетевой латентности; потолок держит троттл сервиса
    marker: str       # gate-файл для scheduled-джобы
    min_interval: float  # троттл сервиса, с/запрос — из него считается размер батча


PROVIDERS: dict[str, Provider] = {
    # min_interval дублирует _ITUNES_MIN_INTERVAL / _MIN_INTERVAL из сервисов
    # намеренно: сервис держит темп, а здесь из того же числа считается батч,
    # который успеет уложиться в _BATCH_TIMEOUT. Разъедутся — вернётся баг
    # «батч всегда в таймаут» (см. _safe_batch).
    "itunes": Provider("itunes", _itunes_lookup, concurrency=2,
                       marker="/app/uploads/.backfill_itunes_enabled",
                       min_interval=3.1),
    "yandex": Provider("yandex", _yandex_lookup, concurrency=3,
                       marker="/app/uploads/.backfill_yandex_enabled",
                       min_interval=0.25),
}

# Watchdog: любой батч обновляет _last_progress; при застое > лимита — self-exit
# (чистый рестарт, resumable). См. инциденты Deezer-воркера.
_STALL_LIMIT = 600
_last_progress = time.monotonic()
_BATCH_TIMEOUT = 240
# Доля таймаута, в которую должен уложиться батч. Запас на латентность самих
# запросов поверх троттла — троттл задаёт паузы МЕЖДУ запросами, а не их время.
_BATCH_FILL = 0.8


async def _watchdog() -> None:
    while True:
        await asyncio.sleep(60)
        stalled = time.monotonic() - _last_progress
        if stalled > _STALL_LIMIT:
            logger.error("backfill stalled %.0fs — self-exit for clean relaunch", stalled)
            os._exit(1)


def _worklist_table(source: str) -> str:
    return f"cover_backfill_masters_{source}"


async def _ensure_infra(source: str) -> None:
    tbl = _worklist_table(source)
    async with async_session_maker() as s:
        await s.execute(text(
            f"CREATE TABLE IF NOT EXISTS {tbl} ("
            "  master_id BIGINT PRIMARY KEY, artist TEXT, title TEXT, year INT,"
            "  done BOOLEAN NOT NULL DEFAULT FALSE)"
        ))
        await s.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{tbl}_todo ON {tbl} (master_id) WHERE NOT done"
        ))
        await s.execute(text(
            "CREATE TABLE IF NOT EXISTS cover_backfill_progress ("
            "  kind TEXT PRIMARY KEY, last_id BIGINT NOT NULL DEFAULT 0,"
            "  seen BIGINT NOT NULL DEFAULT 0, covered BIGINT NOT NULL DEFAULT 0,"
            "  updated_at TIMESTAMP NOT NULL DEFAULT now())"
        ))
        await s.commit()


async def _build_masters_worklist(source: str, rebuild: bool = False) -> int:
    tbl = _worklist_table(source)
    async with async_session_maker() as s:
        await s.execute(text("SET statement_timeout = 120000"))
        if rebuild:
            await s.execute(text(f"TRUNCATE {tbl}"))
            await s.commit()
        have = (await s.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar()
        if have and not rebuild:
            return int(have)
        logger.info("[%s] building masters worklist (heavy agg, ~30s)...", source)
        # Представитель artist/title — версия с наименьшим годом. HAVING bool_and —
        # только мастера, у которых ВСЕ версии без обложки. Уже покрытые в
        # discogs_master_covers (Deezer + прежние источники) исключаем анти-джойном.
        await s.execute(text(
            f"INSERT INTO {tbl} (master_id, artist, title, year) "
            "SELECT i.master_id, "
            "       (array_agg(i.artist ORDER BY i.year NULLS LAST))[1], "
            "       (array_agg(i.title  ORDER BY i.year NULLS LAST))[1], "
            "       min(i.year) "
            "FROM discogs_releases_index i "
            "WHERE i.master_id IS NOT NULL AND i.master_id <> 0 "
            "GROUP BY i.master_id "
            "HAVING bool_and(i.cover_image_url IS NULL) "
            "ON CONFLICT (master_id) DO NOTHING"
        ))
        await s.commit()
        await s.execute(text(
            f"DELETE FROM {tbl} w USING discogs_master_covers mc "
            "WHERE mc.master_id = w.master_id"
        ))
        await s.commit()
        total = (await s.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar()
        logger.info("[%s] masters worklist: %d rows", source, total)
        return int(total)


def _safe_batch(prov: Provider, requested: int) -> int:
    """Батч, который успевает целиком уложиться в _BATCH_TIMEOUT.

    Троттл в сервисах глобальный и последовательный: `concurrency` перекрывает
    только сетевую латентность, темп задаёт `min_interval`. У iTunes это
    3.1 с/запрос, то есть батч из 200 требует 620 с — вдвое больше таймаута.
    Таймаут был бы не аварией, а нормой каждого прогона.
    """
    fits = int(_BATCH_TIMEOUT * _BATCH_FILL / prov.min_interval)
    return max(1, min(requested, fits))


async def _gather_batch(prov: Provider, items: list[dict], sem: asyncio.Semaphore) -> list[dict]:
    """Опросить батч. Возвращает ТОЛЬКО реально опрошенные элементы.

    Это принципиально: вызывающий помечает `done = TRUE` всё, что получил
    отсюда. Раньше таймаут возвращал весь батч (`setdefault("cover", None)`),
    и мастера, до которых очередь не дошла, уходили в done без единого запроса —
    навсегда, потому что worklist больше их не отдаст. При iTunes-троттле это
    съедало бы ~60% очереди вхолостую.
    """
    async def _lookup(item: dict) -> dict:
        async with sem:
            try:
                item["cover"] = await prov.lookup(item["artist"], item["title"], item.get("year"))
            except Exception:
                item["cover"] = None
            # Ставим ПОСЛЕ вызова: отменённая по таймауту корутина сюда не
            # доходит, значит элемент не будет закрыт и вернётся в следующий батч.
            item["attempted"] = True
        return item

    try:
        return await asyncio.wait_for(
            asyncio.gather(*(_lookup(it) for it in items)), timeout=_BATCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        done = [it for it in items if it.get("attempted")]
        logger.warning(
            "[%s] batch timeout (%ds): опрошено %d из %d, остальные вернутся в очередь",
            prov.name, _BATCH_TIMEOUT, len(done), len(items),
        )
        return done


async def _run_masters(prov: Provider, batch: int, max_requests: int | None) -> None:
    global _last_progress
    tbl = _worklist_table(prov.name)
    kind = f"masters_{prov.name}"
    total = await _build_masters_worklist(prov.name)
    if not total:
        logger.info("[%s] masters worklist empty — nothing to do", prov.name)
        return
    sem = asyncio.Semaphore(prov.concurrency)
    batch = _safe_batch(prov, batch)
    seen = covered = 0
    t0 = time.monotonic()

    while True:
        if max_requests is not None and seen >= max_requests:
            break
        async with async_session_maker() as s:
            rows = (await s.execute(text(
                f"SELECT master_id, artist, title, year FROM {tbl} "
                "WHERE NOT done ORDER BY master_id LIMIT :b"
            ), {"b": batch})).mappings().all()
        if not rows:
            break

        items = [dict(r) for r in rows]
        results = await _gather_batch(prov, items, sem)
        if not results:
            # Ни одного опроса за _BATCH_TIMEOUT — источник лежит или троттл
            # встал. Продолжать нельзя: done не проставится, следующий SELECT
            # вернёт те же строки, и цикл закрутится вхолостую навсегда.
            logger.error("[%s] batch: ни одного ответа за %ds — прерываем проход",
                         prov.name, _BATCH_TIMEOUT)
            break
        hits = [r for r in results if r["cover"]]
        done_ids = [r["master_id"] for r in results]
        seen += len(results)
        covered += len(hits)

        async with async_session_maker() as s:
            if hits:
                await s.execute(text(
                    "INSERT INTO discogs_master_covers (master_id, cover_image_url, source) "
                    "SELECT * FROM unnest(CAST(:ids AS bigint[]), CAST(:urls AS text[]), "
                    "  CAST(:src AS text[])) ON CONFLICT (master_id) DO NOTHING"
                ), {
                    "ids": [h["master_id"] for h in hits],
                    "urls": [h["cover"] for h in hits],
                    "src": [prov.name] * len(hits),
                })
            await s.execute(text(
                f"UPDATE {tbl} SET done = TRUE WHERE master_id = ANY(:ids)"
            ), {"ids": done_ids})
            await s.execute(text(
                "INSERT INTO cover_backfill_progress (kind, seen, covered, updated_at) "
                "VALUES (:k, :seen, :cov, now()) "
                "ON CONFLICT (kind) DO UPDATE SET seen=:seen, covered=:cov, updated_at=now()"
            ), {"k": kind, "seen": seen, "cov": covered})
            await s.commit()

        _last_progress = time.monotonic()
        rate = seen / max(time.monotonic() - t0, 1e-9)
        logger.info("[%s] masters: seen=%d covered=%d (%.0f%%) rate=%.1f/s",
                    prov.name, seen, covered, 100 * covered / max(seen, 1), rate)


async def run_scheduled_batch(source: str, batch: int = 200, max_requests: int = 200) -> None:
    """Ограниченный проход worklist для APScheduler-джобы (in-process).

    Гейт — маркер provider.marker. Resumable (done-флаги). Только masters
    (там 1.45M непокрытых; release-хвост при iTunes-троттле 19/min нереалистичен
    из планировщика — гоняется вручную из CLI при желании). БЕЗ _watchdog
    (его os._exit убил бы scheduler); батч ограничен max_requests + _BATCH_TIMEOUT.
    """
    prov = PROVIDERS[source]
    if not os.path.exists(prov.marker):
        return
    await _ensure_infra(source)
    await _run_masters(prov, batch, max_requests)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=list(PROVIDERS), required=True)
    ap.add_argument("--kind", choices=["masters"], default="masters")
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--max-requests", type=int, default=None,
                    help="Остановиться после N просмотров (для теста)")
    ap.add_argument("--rebuild-worklist", action="store_true")
    args = ap.parse_args()

    prov = PROVIDERS[args.source]
    global _last_progress
    _last_progress = time.monotonic()
    wd = asyncio.create_task(_watchdog())
    try:
        await _ensure_infra(args.source)
        if args.rebuild_worklist:
            await _build_masters_worklist(args.source, rebuild=True)
        await _run_masters(prov, args.batch, args.max_requests)
    finally:
        wd.cancel()
    logger.info("[%s] backfill done", args.source)


if __name__ == "__main__":
    asyncio.run(main())
