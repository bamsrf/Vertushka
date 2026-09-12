"""Пересчёт is_collectible по новой формуле — с предпросмотром дельты.

Формула сменилась (см. DiscogsService.compute_is_collectible): вместо «цена
≥$100 + лотов ≤3 + владельцев ≤200» теперь две ветки — спрос (want ≥ 2×have при
цене ≥$100) и цена (≥$500 у релиза с сотней владельцев). Старые значения в
колонках от этого сами не поменяются: флаг ставился один раз и не снимался.

Что пересчитываем и почему не всё подряд:
  * records с is_collectible = TRUE — ложная метка видна юзеру, чиним в первую
    очередь;
  * records с estimated_price_min ≥ $100 — единственные кандидаты получить
    метку впервые (ниже порога ни одна ветка не срабатывает);
  * discogs_releases_index с is_collectible = TRUE — durable-кэш, из него флаг
    расходится на экраны версий;
  * остальным строкам индекса просто обнуляем collectible_checked_at: они
    перепроверятся лениво, когда юзер откроет мастер, — без всплеска запросов
    к Discogs (их там ~2000, это час сетевого времени на ровном месте).

Пересчёт идёт через get_release с предварительным сбросом Redis-кэша релиза —
так значение приходит ровно из того же кода, что и в бою.

Запуск (на проде, в контейнере api):
    docker compose -f docker-compose.prod.yml exec api \\
        python -m scripts.recalc_collectible            # только показать дельту
    docker compose -f docker-compose.prod.yml exec api \\
        python -m scripts.recalc_collectible --apply    # применить

Флаги:
    --apply       Записать изменения (по умолчанию — сухой прогон)
    --delay S     Секунд между релизами (default 1.6 ≈ 37 req/min)
    --limit N     Остановиться после N релизов
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.database import async_session_maker, init_db, close_db
from app.services.cache import cache
from app.services.discogs import DiscogsService
from app.services.rate_limiter import Priority, discogs_limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


#: Вынесены на модуль, чтобы тест мог проверить их компиляцию без живой БД:
#: сломанный плейсхолдер (например постфиксный каст `:id::bigint`) SQLAlchemy
#: молча не распознаёт как параметр, и ошибка вылезает только в проде.
SQL_SET_RECORD = "UPDATE records SET is_collectible = :v WHERE discogs_id = :id"

SQL_SET_INDEX = (
    "UPDATE discogs_releases_index "
    "SET is_collectible = :v, collectible_checked_at = now() "
    "WHERE discogs_id = :did"
)

CANDIDATES_SQL = """
SELECT DISTINCT ON (discogs_id) discogs_id, artist, title, is_collectible, src
FROM (
    SELECT r.discogs_id, r.artist, r.title, r.is_collectible, 'record' AS src
    FROM records r
    WHERE r.discogs_id ~ '^[0-9]+$'
      AND (r.is_collectible IS TRUE OR r.estimated_price_min >= :min_price)
    UNION ALL
    SELECT i.discogs_id::text, i.artist, i.title, i.is_collectible, 'index' AS src
    FROM discogs_releases_index i
    WHERE i.is_collectible IS TRUE
) t
ORDER BY discogs_id, is_collectible DESC
"""


async def _load_candidates() -> list[dict]:
    async with async_session_maker() as db:
        rows = (await db.execute(
            text(CANDIDATES_SQL),
            {"min_price": DiscogsService.COLLECTIBLE_MIN_PRICE_USD},
        )).mappings().all()
    return [dict(r) for r in rows]


async def _recompute(discogs: DiscogsService, discogs_id: str) -> bool | None:
    """Свежий вердикт по релизу. None — «цены нет, вердикта нет».

    Дёргаем ровно два эндпоинта, а не get_release. Формуле нужны только цены и
    community-счётчики; get_release тянет сверх этого мастера и миниатюру
    артиста — вчетверо больше запросов на релиз. На 253 кандидатах это ~2500
    вызовов, то есть 65 req/min против лимита Discogs 60: прогон сам себя
    заваливал 429 и терял вердикт по половине релизов. Два вызова при --delay 6
    дают 20 req/min и оставляют запас живым юзерам.

    Priority.BATCH — скрипт не должен выгребать токены у запросов, которых
    кто-то ждёт в UI.
    """
    try:
        await cache.delete("release", discogs_id)
        await cache.delete("price_stats", discogs_id)
    except Exception:
        logger.debug("cache drop failed for %s", discogs_id, exc_info=True)

    stats = await discogs._get_price_stats(discogs_id)
    release = await discogs._get(
        f"{discogs.BASE_URL}/releases/{discogs_id}",
        headers=discogs._get_token_headers(),
        priority=Priority.BATCH,
    )
    community = release.get("community") or {}
    return DiscogsService.compute_is_collectible(
        stats, community.get("have"), community.get("want")
    )


async def _apply(discogs_id: str, value: bool) -> bool:
    """Пишет флаг в records и в durable-индекс. True, если записалось.

    discogs_id в records — текст, в discogs_releases_index — bigint. Приводим
    типы в Python, а не в SQL: постфиксный каст `:id::bigint` ломает парсер
    text() — он видит `:id:` и падает синтаксической ошибкой. Из-за этого
    первый прогон с --apply записал НОЛЬ изменений: оба UPDATE шли одной
    транзакцией, второй валился, первый откатывался вместе с ним.
    """
    try:
        async with async_session_maker() as db:
            await db.execute(text(SQL_SET_RECORD), {"v": value, "id": discogs_id})
            await db.execute(
                text(SQL_SET_INDEX), {"v": value, "did": int(discogs_id)}
            )
            await db.commit()
        return True
    except Exception:
        # Одна сбойная строка не должна уносить прогон: остальные 250 записей
        # ни при чём, а перезапуск стоит получаса сетевого времени.
        logger.exception("Не удалось записать флаг для %s", discogs_id)
        return False


async def _invalidate_negative_index() -> int:
    """Сбрасываем окно свежести у «проверено и не редкий».

    Эти строки считались по старым порогам, где спрос не учитывался вовсе.
    Обнулённый collectible_checked_at заставит фоновое обогащение перепроверить
    их по новой формуле — лениво, по мере открытия мастеров.
    """
    async with async_session_maker() as db:
        res = await db.execute(text(
            "UPDATE discogs_releases_index SET collectible_checked_at = NULL "
            "WHERE is_collectible IS NOT TRUE AND collectible_checked_at IS NOT NULL"
        ))
        await db.commit()
        return res.rowcount or 0


async def run(apply: bool, delay: float, limit: int | None) -> None:
    """Прогон по кандидатам. Ошибки не персистятся — релиз, по которому Discogs
    не ответил, останется с прежним флагом и попадёт в следующий прогон."""
    await init_db()
    candidates = await _load_candidates()
    if limit:
        candidates = candidates[:limit]

    logger.info(
        "Кандидатов: %d%s", len(candidates), "" if apply else "  [СУХОЙ ПРОГОН]",
    )
    if not candidates:
        await close_db()
        return

    discogs_limiter.start()
    discogs = DiscogsService()

    set_on: list[dict] = []
    set_off: list[dict] = []
    unknown: list[dict] = []
    failed = 0
    write_failed = 0

    for i, row in enumerate(candidates, 1):
        did = row["discogs_id"]
        was = bool(row["is_collectible"])
        try:
            now = await _recompute(discogs, did)
        except Exception as e:
            failed += 1
            logger.warning("get_release failed for %s: %s", did, e)
            await asyncio.sleep(delay)
            continue

        label = f"{row['artist']} — {row['title']}"[:52]
        if now is None:
            if was:
                unknown.append(row)
                logger.info("[%d/%d] %s · %s → цены нет, метку оставляем", i, len(candidates), did, label)
        elif now and not was:
            set_on.append(row)
            logger.info("[%d/%d] %s · %s → СТАВИМ", i, len(candidates), did, label)
            if apply and not await _apply(did, True):
                write_failed += 1
        elif was and not now:
            set_off.append(row)
            logger.info("[%d/%d] %s · %s → СНИМАЕМ", i, len(candidates), did, label)
            if apply and not await _apply(did, False):
                write_failed += 1

        await asyncio.sleep(delay)

    logger.info(
        "Итог: ставим %d · снимаем %d · без вердикта %d · ошибок %d%s%s",
        len(set_on), len(set_off), len(unknown), failed,
        f" · НЕ ЗАПИСАЛОСЬ {write_failed}" if write_failed else "",
        "" if apply else "  (ничего не записано, это сухой прогон)",
    )
    for title, rows in (("СТАВИМ", set_on), ("СНИМАЕМ", set_off)):
        if rows:
            logger.info("--- %s:", title)
            for r in rows:
                logger.info("    %s  %s — %s", r["discogs_id"], r["artist"], r["title"])

    if apply:
        reset = await _invalidate_negative_index()
        logger.info("Сброшено окно свежести у %d строк индекса — перепроверятся лениво", reset)

    discogs_limiter.stop()
    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересчёт is_collectible по новой формуле")
    parser.add_argument("--apply", action="store_true", help="Записать изменения")
    parser.add_argument("--delay", type=float, default=6.0,
                        help="Секунд между релизами (2 вызова каждый: 6с ≈ 20 req/min)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, delay=args.delay, limit=args.limit))


if __name__ == "__main__":
    main()
