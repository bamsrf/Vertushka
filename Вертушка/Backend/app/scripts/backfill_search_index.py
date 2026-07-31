"""Досыпать в discogs_releases_index записи, добытые живым Discogs-фетчем.

Проблема: релиз, найденный матчером листингов через живой Discogs API (когда
дампа он не застал — дамп режется на дату), создавал Record, но в
discogs_releases_index не попадал. Каталог знал пластинку, /records/search —
нет. Классика: Антоха МС «Родня» 2026 (discogs_id=37436703) есть в records,
но поиск отдаёт только «Родня» 2016 из дампа (да ещё и File, FLAC).

Точечный фикс в listing_matcher._save_discogs_result закрывает поток вперёд;
этот скрипт разбирает то, что накопилось до него.

Discogs НЕ дёргаем — все нужные поля уже лежат в records. Идемпотентно
(ON CONFLICT DO NOTHING), можно гонять повторно.

Запуск на проде:
  docker compose -f docker-compose.prod.yml exec -T api \
    python -m app.scripts.backfill_search_index

Сначала посмотреть объём, ничего не меняя:
  ... python -m app.scripts.backfill_search_index --dry-run
"""
import argparse
import asyncio
import logging

from sqlalchemy import text

from app.database import async_session_maker
from app.services.discogs_index import upsert_release_into_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_search_index")

# Записи с discogs_id, которых нет в индексе. Приведение к bigint — в records
# discogs_id это varchar, в индексе bigint; нечисловые мусорные id отсекаем
# регуляркой до каста, иначе упадёт вся выборка.
_SELECT = """
SELECT r.discogs_id, r.discogs_master_id, r.artist, r.title, r.year,
       r.country, r.format_type, r.label, r.barcode, r.catalog_number,
       r.cover_image_url
FROM records r
WHERE r.source = 'discogs'
  AND r.discogs_id IS NOT NULL
  AND r.discogs_id ~ '^[0-9]+$'
  AND r.merged_into_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM discogs_releases_index d
      WHERE d.discogs_id = r.discogs_id::bigint
  )
ORDER BY r.created_at DESC
LIMIT :lim OFFSET :off
"""


async def run(batch_size: int, dry_run: bool) -> None:
    seen = written = 0
    offset = 0

    while True:
        async with async_session_maker() as db:
            rows = (await db.execute(
                text(_SELECT), {"lim": batch_size, "off": offset}
            )).mappings().all()

            if not rows:
                break

            seen += len(rows)

            if dry_run:
                # Ничего не пишем → следующая страница берётся смещением.
                offset += batch_size
                for r in rows[:5]:
                    logger.info("  [dry] %s — %s — %s (%s)",
                                r["discogs_id"], r["artist"], r["title"], r["year"])
                logger.info("dry-run: осмотрено %d", seen)
                continue

            for r in rows:
                await upsert_release_into_index(db, {
                    "id": r["discogs_id"],
                    "master_id": r["discogs_master_id"],
                    "artist": r["artist"],
                    "title": r["title"],
                    "year": r["year"],
                    "country": r["country"],
                    "format": r["format_type"],
                    "label": r["label"],
                    "barcode": r["barcode"],
                    "catalog_number": r["catalog_number"],
                    "cover_image": r["cover_image_url"],
                })
                written += 1

            await db.commit()

        # Без dry-run обработанные выпадают из выборки (NOT EXISTS уже ложь),
        # поэтому offset не двигаем — иначе перескочим через хвост.
        logger.info("прогресс: осмотрено=%d записано=%d", seen, written)

    logger.info("готово: осмотрено=%d записано=%d", seen, written)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true",
                    help="только посчитать и показать примеры, без записи")
    args = ap.parse_args()
    asyncio.run(run(args.batch_size, args.dry_run))


if __name__ == "__main__":
    main()
