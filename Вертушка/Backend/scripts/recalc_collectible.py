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
from app.services.rate_limiter import discogs_limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


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
    """Свежий вердикт по релизу. None — «цены нет, вердикта нет»."""
    try:
        await cache.delete("release", discogs_id)
        await cache.delete("price_stats", discogs_id)
    except Exception:
        logger.debug("cache drop failed for %s", discogs_id, exc_info=True)
    data = await discogs.get_release(discogs_id)
    return data.get("is_collectible")


async def _apply(discogs_id: str, value: bool) -> None:
    async with async_session_maker() as db:
        await db.execute(
            text("UPDATE records SET is_collectible = :v WHERE discogs_id = :id"),
            {"v": value, "id": discogs_id},
        )
        await db.execute(
            text(
                "UPDATE discogs_releases_index "
                "SET is_collectible = :v, collectible_checked_at = now() "
                "WHERE discogs_id = :id::bigint"
            ),
            {"v": value, "id": discogs_id},
        )
        await db.commit()


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
            if apply:
                await _apply(did, True)
        elif was and not now:
            set_off.append(row)
            logger.info("[%d/%d] %s · %s → СНИМАЕМ", i, len(candidates), did, label)
            if apply:
                await _apply(did, False)

        await asyncio.sleep(delay)

    logger.info(
        "Итог: ставим %d · снимаем %d · без вердикта %d · ошибок %d%s",
        len(set_on), len(set_off), len(unknown), failed,
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
    parser.add_argument("--delay", type=float, default=1.6)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, delay=args.delay, limit=args.limit))


if __name__ == "__main__":
    main()
