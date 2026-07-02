"""CLI: bulk-прогрев обложек Cover Art Archive по маппингу mb_discogs_map.

Для каждой строки discogs_releases_index без cover_image_url, у которой есть
MBID в mb_discogs_map и которую ещё не проверяли (caa_checked_at IS NULL):

  HEAD https://coverartarchive.org/release/{mbid}/front-1200
    30x → обложка есть → пишем URL в discogs_releases_index.cover_image_url
    404 → обложки нет
  в обоих случаях ставим mb_discogs_map.caa_checked_at = now()

CAA официально без rate limit, но хостится на archive.org — держим вежливые
--rps (default 5). При 429/5xx — экспоненциальный backoff.

Прогон возобновляемый: фильтр caa_checked_at IS NULL сам продолжает с места
остановки, скрипт можно убивать/перезапускать в любой момент.

Использование (на проде, в фоне; при 5 rps ~400K проверок/сутки):

  ssh deploy@... 'docker exec -d vertushka_api sh -c \
    "python -m app.scripts.warm_caa_covers > /tmp/caa_warm.log 2>&1"'
  ssh deploy@... 'docker exec vertushka_api tail -f /tmp/caa_warm.log'

Параметры:
  --rps N     запросов в секунду к CAA (default: 5)
  --limit N   максимум проверок за прогон (для тестов)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

import httpx
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("caa_warm")

_CAA_FRONT = "https://coverartarchive.org/release/{mbid}/front-1200"
_DB_BATCH = 500
_CONCURRENCY = 8


async def _check_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    pace: "_Pacer",
    discogs_id: int,
    mbid: str,
) -> tuple[int, str | None]:
    """Возвращает (discogs_id, cover_url | None). Ошибки сети = None,
    но строка всё равно будет помечена checked — CAA стабилен, повторная
    массовая перепроверка дороже единичных ложных промахов."""
    async with sem:
        await pace.wait()
        url = _CAA_FRONT.format(mbid=mbid)
        backoff = 2.0
        for _ in range(4):
            try:
                resp = await client.head(url, follow_redirects=False)
            except httpx.HTTPError:
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code in (301, 302, 307):
                return discogs_id, url
            if resp.status_code in (429, 503, 502, 500):
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            return discogs_id, None  # 404 и прочее — обложки нет
        return discogs_id, None


class _Pacer:
    """Глобальный троттл N rps поверх семафора конкурентности."""

    def __init__(self, rps: float) -> None:
        self._interval = 1.0 / rps
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delta = self._interval - (time.monotonic() - self._last)
            if delta > 0:
                await asyncio.sleep(delta)
            self._last = time.monotonic()


async def warm(rps: float, limit: int | None) -> None:
    headers = {"User-Agent": get_settings().discogs_user_agent}
    sem = asyncio.Semaphore(_CONCURRENCY)
    pace = _Pacer(rps)
    total_checked = 0
    total_found = 0
    started = time.monotonic()

    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        while True:
            take = _DB_BATCH if limit is None else min(_DB_BATCH, limit - total_checked)
            if take <= 0:
                break

            async with async_session_maker() as session:
                rows = (await session.execute(
                    text(
                        "SELECT m.discogs_id, m.mbid::text AS mbid "
                        "FROM mb_discogs_map m "
                        "JOIN discogs_releases_index d ON d.discogs_id = m.discogs_id "
                        "WHERE m.caa_checked_at IS NULL "
                        "AND d.cover_image_url IS NULL "
                        "ORDER BY d.year DESC NULLS LAST "
                        "LIMIT :n"
                    ),
                    {"n": take},
                )).mappings().all()

                if not rows:
                    break

                results = await asyncio.gather(*[
                    _check_one(client, sem, pace, r["discogs_id"], r["mbid"])
                    for r in rows
                ])

                found = [(did, url) for did, url in results if url]
                if found:
                    await session.execute(
                        text(
                            "UPDATE discogs_releases_index SET cover_image_url = v.url "
                            "FROM (SELECT unnest(CAST(:ids AS bigint[])) AS did, "
                            "             unnest(CAST(:urls AS text[])) AS url) v "
                            "WHERE discogs_id = v.did AND cover_image_url IS NULL"
                        ),
                        {"ids": [d for d, _ in found], "urls": [u for _, u in found]},
                    )
                await session.execute(
                    text(
                        "UPDATE mb_discogs_map SET caa_checked_at = now() "
                        "WHERE discogs_id = ANY(:ids)"
                    ),
                    {"ids": [r["discogs_id"] for r in rows]},
                )
                await session.commit()

            total_checked += len(rows)
            total_found += len(found)
            elapsed = time.monotonic() - started
            logger.info(
                "checked=%d found=%d (%.0f%%) rate=%.1f rps",
                total_checked, total_found,
                100.0 * total_found / max(total_checked, 1),
                total_checked / max(elapsed, 1),
            )

    logger.info("ГОТОВО: %d проверено, %d обложек найдено", total_checked, total_found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rps", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(warm(args.rps, args.limit))


if __name__ == "__main__":
    main()
