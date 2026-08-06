"""CLI: CSV.gz полных описаний формата → discogs_release_formats.

Вторая половина пары к `extract_release_formats` (тот запускается НЕ на проде —
`data.discogs.com` встречает сервер JS-челленджем Cloudflare). Сюда приезжает
CSV `discogs_id,format_full` и льётся COPY-батчами через staging.

Диск на проде тесный (~4.3 ГБ свободно при ожидаемой ~1.2 ГБ таблице), поэтому:
  * COPY, а не построчный INSERT;
  * `--truncate` для полной перезаливки вместо UPDATE (иначе heap удваивается
    до VACUUM FULL, а на него места нет);
  * грузим только релизы, которые есть в индексе — в дампе 19.3M, в индексе
    13.1M, остальные 4.2M строк легли бы мёртвым грузом.

## Грабли, на которые уже наступили

Staging чистится **явным TRUNCATE**, а не через `ON COMMIT DELETE ROWS`.
asyncpg работает в автокоммите: COPY коммитится сам, и `ON COMMIT` сносил
staging ДО того, как отрабатывал `INSERT ... SELECT`. Загрузчик прочитывал все
12.7M строк, вставлял ноль и рапортовал об успехе. Та же конструкция живёт в
`ingest_discogs_dump._copy_batch` под флагом `--skip-existing` — если тот
ingest когда-то возобновляли с этим флагом, он так же молча не вставлял ничего.

Соединение одно на весь прогон: staging-таблица временная и умирает вместе с
сессией, так что открывать коннект на каждый батч бессмысленно.

Идемпотентность: ON CONFLICT DO UPDATE — повторный прогон обновляет строки,
дельта-дамп поверх полного ложится без чистки.

Использование:

    docker exec vertushka_api python -m app.scripts.load_release_formats \\
      --file /tmp/formats_20260801.csv.gz --dump-date 2026-08-01 --truncate
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import logging
import sys
import time
from datetime import date
from pathlib import Path

from app.database import engine

logger = logging.getLogger("load_release_formats")

_BATCH = 20_000

_UPSERT = """
WITH ins AS (
    INSERT INTO discogs_release_formats (discogs_id, format_full, dump_version)
    SELECT s.discogs_id, s.format_full, s.dump_version
    FROM _fmt_stage s
    -- Только релизы, реально существующие в индексе: в дампе 19.3M, в индексе
    -- 13.1M (66.8%). Без фильтра 4.2M строк (~450 МБ) заняли бы диск, ни к
    -- чему не присоединяясь.
    WHERE EXISTS (
        SELECT 1 FROM discogs_releases_index i WHERE i.discogs_id = s.discogs_id
    )
    ON CONFLICT (discogs_id) DO UPDATE
        SET format_full = EXCLUDED.format_full,
            dump_version = EXCLUDED.dump_version
    RETURNING 1
)
SELECT COUNT(*) FROM ins
"""


async def _flush(pg, rows: list[tuple]) -> int:
    if not rows:
        return 0
    await pg.execute("TRUNCATE _fmt_stage")
    await pg.copy_records_to_table(
        "_fmt_stage", records=rows,
        columns=("discogs_id", "format_full", "dump_version"),
    )
    return int(await pg.fetchval(_UPSERT) or 0)


async def load(file_path: Path, dump_date: date, truncate: bool) -> dict[str, int]:
    counters = {"read": 0, "loaded": 0, "bad": 0}
    started = time.time()
    last_report = started
    batch: list[tuple] = []

    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        pg = raw.driver_connection

        if truncate:
            await pg.execute("TRUNCATE discogs_release_formats")
            logger.info("таблица очищена — полная перезаливка")
        await pg.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _fmt_stage "
            "(LIKE discogs_release_formats INCLUDING DEFAULTS)"
        )

        with gzip.open(file_path, "rt", encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) != 2 or not row[0].isdigit() or not row[1]:
                    counters["bad"] += 1
                    continue
                batch.append((int(row[0]), row[1], dump_date))
                counters["read"] += 1
                if len(batch) >= _BATCH:
                    counters["loaded"] += await _flush(pg, batch)
                    batch = []
                    now = time.time()
                    if now - last_report >= 30:
                        logger.info(
                            "read=%d loaded=%d bad=%d rate=%.0f/s",
                            counters["read"], counters["loaded"], counters["bad"],
                            counters["read"] / (now - started),
                        )
                        last_report = now
        counters["loaded"] += await _flush(pg, batch)

    logger.info(
        "ГОТОВО за %.1f мин: read=%d loaded=%d bad=%d",
        (time.time() - started) / 60,
        counters["read"], counters["loaded"], counters["bad"],
    )
    if counters["read"] and not counters["loaded"]:
        logger.error(
            "прочитано %d строк, вставлено 0 — это не норма, проверь staging",
            counters["read"],
        )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dump-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--truncate", action="store_true",
        help="очистить таблицу перед заливкой (полная перезаливка)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    if not args.file.exists():
        parser.error(f"нет файла: {args.file}")

    asyncio.run(load(args.file, date.fromisoformat(args.dump_date), args.truncate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
