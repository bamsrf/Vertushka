"""CLI: CSV.gz цветов пресса из дампа → `records.discogs_data->>'vinyl_color_raw'`.

## Зачем

Чип «Цветной винил» фильтрует по `store_listings.vinyl_color_raw`, а цвет
заполняют два маленьких магазина из девяти: у stoprobotvinyl он есть у всех
1632 позиций, у korobkavinyla у 361 из 691 — и при этом у skifmusic 34 из
18 315, у vinylhouse 0 из 12 053. Весь цветной пул — около 985 карточек.

Discogs же знает цвет пресса: он лежит в атрибуте `text` у формата и приезжает
в дампе. По нашим 37 464 записям (дамп 2026-08) цвет распознаётся у 6 436, из
них 943 описывают упаковку («Metallic Silver Sleeve», «Green Case») и
отбрасываются — остаётся 4 779 записей, то есть +3 578 карточек в чипе.

## Куда кладём и почему туда

В `discogs_data->>'vinyl_color_raw'` — ровно то поле, куда цвет пишет живой
путь через Discogs API (`api/records.py`), и откуда его читают карточка записи
(`display_vinyl_color`) и батч-агрегат офферов. Источник другой, смысл тот же,
так что и место то же: цвет заодно появится на карточке, а не только в фильтре.

## Чего этот цвет НЕ утверждает

Это цвет РЕЛИЗА, к которому примотан листинг, а не самого объявления магазина.
Там, где матч опознал конкретный пресс (штрихкод, каталожный номер), он верен;
на нечётких матчах может относиться к другому прессу того же альбома. Решение
осознанное: год, страну, лейбл и формат карточка уже показывает из этой же
записи, и цвет тут не спекулятивнее остального. Точный подметод матча
`dump_index` пока не пишет — когда начнёт, фильтр можно будет ужесточить.

Использование:

    docker exec vertushka_api python -m app.scripts.load_release_colors \\
      --file /tmp/colors_20260801.csv.gz [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import logging
import sys
import time
from pathlib import Path

from app.database import engine

logger = logging.getLogger("load_release_colors")

_BATCH = 10_000

#: Не перетираем уже известный цвет: он либо из живого API (свежее дампа), либо
#: из самого листинга. Обновляем только записи, где поля нет или оно пустое.
_WHERE = """
    WHERE r.discogs_id ~ '^[0-9]+$'
      AND r.discogs_id::bigint = s.discogs_id
      AND r.merged_into_id IS NULL
      AND COALESCE(r.discogs_data->>'vinyl_color_raw', '') = ''
"""

_UPDATE = f"""
WITH upd AS (
    UPDATE records r
    -- Проверяем jsonb_typeof, а не COALESCE на NULL. SQLAlchemy кладёт
    -- питоновский None в JSONB-колонку как JSON-null, а не как SQL NULL, и
    -- COALESCE его не ловит: `'null'::jsonb || '{{"k":"v"}}'` даёт МАССИВ
    -- [null, {{...}}], а не объект. Поймано интеграционным тестом на живой базе.
    SET discogs_data = (
            CASE WHEN jsonb_typeof(r.discogs_data) = 'object'
                 THEN r.discogs_data ELSE '{{}}'::jsonb END
        ) || jsonb_build_object('vinyl_color_raw', s.color),
        updated_at = NOW()
    FROM _color_stage s
    {_WHERE}
    RETURNING 1
)
SELECT COUNT(*) FROM upd
"""

_COUNT = f"SELECT COUNT(DISTINCT r.id) FROM records r, _color_stage s {_WHERE}"


async def _flush(pg, rows: list[tuple], dry_run: bool) -> int:
    if not rows:
        return 0
    await pg.execute("TRUNCATE _color_stage")
    await pg.copy_records_to_table(
        "_color_stage", records=rows, columns=("discogs_id", "color"),
    )
    return int(await pg.fetchval(_COUNT if dry_run else _UPDATE) or 0)


async def load(file_path: Path, dry_run: bool) -> dict[str, int]:
    counters = {"read": 0, "updated": 0, "bad": 0}
    started = time.time()
    batch: list[tuple] = []

    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        pg = raw.driver_connection
        # TRUNCATE явным вызовом, а не ON COMMIT DELETE ROWS: asyncpg в
        # автокоммите, COPY коммитится сам, и ON COMMIT снёс бы staging ДО
        # UPDATE. В load_release_formats это уже стоило молчаливой заливки нуля.
        await pg.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _color_stage "
            "(discogs_id bigint, color text)"
        )

        with gzip.open(file_path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) != 2 or not row[0].isdigit() or not row[1].strip():
                    counters["bad"] += 1
                    continue
                batch.append((int(row[0]), row[1].strip()))
                counters["read"] += 1
                if len(batch) >= _BATCH:
                    counters["updated"] += await _flush(pg, batch, dry_run)
                    batch = []
        counters["updated"] += await _flush(pg, batch, dry_run)

    logger.info(
        "ГОТОВО за %.1f мин: read=%d %s=%d bad=%d",
        (time.time() - started) / 60, counters["read"],
        "подошло бы" if dry_run else "обновлено", counters["updated"], counters["bad"],
    )
    if counters["read"] and not counters["updated"]:
        logger.error(
            "прочитано %d строк, изменено 0 — либо цвет уже всюду проставлен, "
            "либо CSV собран не с этой базы",
            counters["read"],
        )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="только посчитать")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout,
    )
    if not args.file.exists():
        parser.error(f"нет файла: {args.file}")
    asyncio.run(load(args.file, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
