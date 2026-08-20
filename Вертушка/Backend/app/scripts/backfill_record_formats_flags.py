"""Бэкфилл format_description и rarity-флагов из уже имеющихся данных.

Исторически полный Discogs-payload складывался в `records.discogs_data` (JSON),
но не доносился до колонок `format_description` / `is_limited` /
`is_collectible` / `is_hot`, по которым считают ачивки (BX/FMT/C-серии),
фильтры Маркета и pricing/valuation. Живой конвейер починен
(_apply_discogs_release + оба места создания Record); этот скрипт добивает
уже существующие записи.

Три источника по приоритету:
1. `discogs_data` — у обогащённых записей там готовые format_description и все
   три флага (включая collectible/hot, которые из дампа не восстановить).
2. `discogs_release_formats.format_full` (дамп) — format_description для
   записей с многодескрипторным форматом.
3. Токен-парс строк формата (`DiscogsService.LIMITED_TOKENS`) → is_limited:
   структурный маркер, восстанавливается без API.

Только заполнение пустого/False: непустые format_description и True-флаги не
трогаем. Идемпотентен — повторный запуск обновит 0 строк.

После прогона ничего выдавать не нужно: ближайший daily_tick ачивок сам
довыдаст C-серию и форматные по обновлённым колонкам.

Запуск (на проде, внутри backend-контейнера):
  python -m app.scripts.backfill_record_formats_flags
  python -m app.scripts.backfill_record_formats_flags --dry-run
"""
import argparse
import asyncio
import logging

from sqlalchemy import text

from app.database import async_session_maker, engine
from app.services.discogs import DiscogsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_formats_flags")


#: (описание, SQL). Порядок важен: format_description заполняем ДО токен-парса
#: is_limited — блоб для поиска токенов становится богаче.
_STATEMENTS: list[tuple[str, str]] = [
    (
        "format_description из discogs_data",
        """
        UPDATE records
        SET format_description = discogs_data->>'format_description'
        WHERE (format_description IS NULL OR format_description = '')
          AND COALESCE(discogs_data->>'format_description', '') <> ''
        """,
    ),
    (
        "format_description из дампа (discogs_release_formats)",
        """
        UPDATE records r
        SET format_description = f.format_full
        FROM discogs_release_formats f
        WHERE (r.format_description IS NULL OR r.format_description = '')
          AND r.discogs_id ~ '^[0-9]+$'
          AND f.discogs_id = r.discogs_id::bigint
        """,
    ),
    (
        "is_limited из discogs_data",
        """
        UPDATE records
        SET is_limited = TRUE
        WHERE is_limited IS NOT TRUE
          AND (discogs_data->>'is_limited')::boolean IS TRUE
        """,
    ),
    (
        "is_collectible из discogs_data",
        """
        UPDATE records
        SET is_collectible = TRUE
        WHERE is_collectible IS NOT TRUE
          AND (discogs_data->>'is_collectible')::boolean IS TRUE
        """,
    ),
    (
        "is_hot из discogs_data",
        """
        UPDATE records
        SET is_hot = TRUE
        WHERE is_hot IS NOT TRUE
          AND (discogs_data->>'is_hot')::boolean IS TRUE
        """,
    ),
]


def _limited_token_sql() -> str:
    """UPDATE для is_limited токен-парсом строк формата.

    Тот же список токенов и та же substring-семантика, что в
    DiscogsService._compute_rarity_flags и cheap-парсе поисковой выдачи.
    Токены — статичные литералы класса, не пользовательский ввод.
    """
    blob = "lower(coalesce(format_type,'') || ' ' || coalesce(format_description,''))"
    conditions = " OR ".join(
        f"{blob} LIKE '%{token}%'" for token in DiscogsService.LIMITED_TOKENS
    )
    return f"""
        UPDATE records
        SET is_limited = TRUE
        WHERE is_limited IS NOT TRUE
          AND ({conditions})
    """


async def backfill(dry_run: bool) -> None:
    statements = _STATEMENTS + [("is_limited токен-парсом строк формата", _limited_token_sql())]
    async with async_session_maker() as db:
        total = 0
        for label, sql in statements:
            result = await db.execute(text(sql))
            count = result.rowcount or 0
            total += count
            logger.info("%s: %d строк", label, count)
        if dry_run:
            await db.rollback()
            logger.info("[dry-run] откат, итого было бы обновлено: %d", total)
        else:
            await db.commit()
            logger.info("Готово, обновлено строк (суммарно по шагам): %d", total)
            logger.info("Ачивки довыдаст ближайший daily_tick (6:00).")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill format_description и rarity-флагов records"
    )
    parser.add_argument("--dry-run", action="store_true", help="Посчитать и откатить")
    return parser.parse_args()


async def _amain() -> None:
    args = _parse_args()
    try:
        await backfill(dry_run=args.dry_run)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_amain())
