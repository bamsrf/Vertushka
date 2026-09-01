"""CLI: проставить `store_listings.vinyl_color_raw` из текста объявления.

## Зачем

Цвет винила парсят два маленьких магазина из девяти. Замер 28.08.2026 по
листингам в наличии: stoprobotvinyl 1632 из 1632, korobkavinyla 361 из 691,
doctorhead 149 из 2224 — и при этом skifmusic 34 из 18 315, plastinka_com 137
из 7671, vinylhouse и long_play по нулю. Из-за этого весь «цветной» пул
Маркета — около 800 карточек, и любой жанровый срез по нему даёт десятки:
регги 14, классика 8. Со стороны это выглядит как потолок выдачи.

При этом текст объявления цвет содержит: «(цветной винил)» стоит в заголовке у
883 позиций plastinka_com, ещё 90 русских и 76 английских упоминаний
конкретного цвета рядом со словом-носителем.

Новые листинги цвет получают сами — `runner._upsert_listing` зовёт
`extract_vinyl_color`, когда парсер ничего не дал. Этот скрипт — разовый
догон уже собранных.

## Осторожно

Заполняем ТОЛЬКО пустые: распарсенное магазином точнее вытащенного из
заголовка. Цвет ищется вплотную к слову-носителю, иначе «Black Sabbath» и
«Fear Of A Black Planet (цветной винил)» дали бы «black».

Использование:

    docker exec vertushka_api python -m app.scripts.backfill_vinyl_color_from_text [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from sqlalchemy import select, update

from app.database import async_session_maker
from app.models.store_listing import StoreListing
from app.services.scrapers.extractors import infer_vinyl_color

logger = logging.getLogger("backfill_vinyl_color")

_CHUNK = 2000


async def run(dry_run: bool) -> dict[str, int]:
    counters = {"scanned": 0, "found": 0, "updated": 0}
    started = time.time()
    last_id = None

    while True:
        async with async_session_maker() as db:
            q = (
                select(StoreListing.id, StoreListing.title_raw)
                .where(StoreListing.vinyl_color_raw.is_(None))
                .order_by(StoreListing.id)
                .limit(_CHUNK)
            )
            if last_id is not None:
                q = q.where(StoreListing.id > last_id)
            rows = (await db.execute(q)).all()
            if not rows:
                break
            last_id = rows[-1][0]
            counters["scanned"] += len(rows)

            # require_cue: в title_raw лежит НАЗВАНИЕ АЛЬБОМА, вырезать его
            # нечем — без строгого режима «Blue Train» стал бы синим винилом.
            found = [
                (lid, color)
                for lid, title in rows
                if (color := infer_vinyl_color(title, require_cue=True))
            ]
            counters["found"] += len(found)
            if found and not dry_run:
                for lid, color in found:
                    await db.execute(
                        update(StoreListing)
                        .where(StoreListing.id == lid)
                        .values(vinyl_color_raw=color[:255])
                    )
                await db.commit()
                counters["updated"] += len(found)

        logger.info("scanned=%d found=%d", counters["scanned"], counters["found"])

    logger.info(
        "ГОТОВО за %.1f мин: %s", (time.time() - started) / 60, counters,
    )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="только посчитать")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout,
    )
    asyncio.run(run(args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
