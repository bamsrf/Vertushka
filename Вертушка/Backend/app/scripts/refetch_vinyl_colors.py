"""Ре-фетч цвета пресса у записей, которым его испортил старый парсер.

## Зачем

До фикса живой фетч брал `formats[0].get("text")` дословно, без фильтра
упаковки и не заглядывая в остальные форматы. В базе от этого два класса
битых значений (замер прода 12.09, 6 390 записей с непустым цветом):

  * 772 записи держат в поле цвета МУСОР: «Gatefold» ×100, «180 Gram» ×28,
    названия заводов («Pitman Pressing», «Terre Haute»), битрейты. Настоящий
    цвет у части из них лежал в formats[1] и просто не доехал;
  * 209 из них — хуже, чем мусор: там цвет ЭТИКЕТКИ или конверта, и он
    выводится как цвет пластинки. «Red Labels» → red ×29, «White Labels» →
    white ×23, «Blue Labels» → blue ×13. Эти ложные цвета шли в «Радугу» и в
    счётчик цветных в профиле.

Починка парсера (`_vinyl_color_from_formats`) лечит только ЗАПИСЬ новых
данных. Существующие строки задним числом не пересчитать: полный массив
`formats` в `discogs_data` не сохраняется, единственный способ узнать правду —
сходить в Discogs заново. Этим и занят скрипт.

## Режимы

  --mode junk     (по умолчанию) только записи, чей сохранённый цвет
                  исправленный парсер забраковал бы. ~750 записей, ~3 часа.
                  Именно здесь лежит вся ложь, ради которой всё затевалось.

  --mode missing  записи вообще без цвета. Их 46 796 — это несколько СУТОК,
                  поэтому режим только по явному флагу и всегда с --limit.
                  Улов будет жидкий: у большинства цвета нет и у Discogs.

Про темп. Считать «60 rpm = запись в секунду» НЕЛЬЗЯ, и первая оценка этого
скрипта была занижена в десять раз именно так. `get_release` тратит на одну
пластинку несколько запросов (сам релиз, миниатюра артиста, статистика цен), а
бакет ещё и делится со всем, что в этот момент ходит в Discogs, — замер на
проде 12.09 дал ~14 секунд на запись при параллельно идущем пересчёте
коллекционности. Планируй по 10-15 с/запись, а не по секунде.

## Что именно меняется

Только ключ `vinyl_color_raw` внутри `discogs_data`, остальное не трогаем
(`||` поверх объекта, а не перезапись). Новый цвет не распознан — ключ
УДАЛЯЕТСЯ, а не переписывается пустышкой: «Gatefold» в поле цвета хуже, чем
отсутствие цвета.

Рядом пишется `vinyl_color_checked_at`. Он нужен для возобновляемости: без
него запись, у которой цвета нет и у Discogs, попадала бы в выборку --mode
missing при каждом следующем запуске, и скрипт вечно долбил бы одни и те же
строки.

## Осторожно: кэш

`get_release` кэшируется в Redis, и там лежит payload, разобранный СТАРЫМ
парсером. Без сброса кэша скрипт бодро «перезаписал» бы то же самое значение.
Поэтому перед каждым запросом ключ релиза инвалидируется.

Usage:
  # Контейнер API называется vertushka_api_blue / _green (blue-green деплой),
  # а не vertushka_api — точное имя смотри в `docker ps`.
  docker exec vertushka_api_blue python -m app.scripts.refetch_vinyl_colors \\
      [--mode junk|missing] [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import text

from app.database import async_session_maker
from app.services.vinyl_color import vinyl_color_from_format_texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("refetch_vinyl_colors")

#: Записи, у которых цвет вообще есть. Разбраковку делаем в Python: «забракует
#: ли исправленный парсер это значение» — вопрос той же функции, что и на
#: записи, и дублировать её регулярками в SQL значит завести второй источник
#: правды (на этом уже обжигались с profile_stats).
_SELECT_WITH_COLOR = """
    SELECT id, discogs_id, discogs_data->>'vinyl_color_raw' AS color
    FROM records
    WHERE discogs_id ~ '^[0-9]+$'
      AND merged_into_id IS NULL
      AND COALESCE(discogs_data->>'vinyl_color_raw', '') <> ''
      AND discogs_data->>'vinyl_color_checked_at' IS NULL
    ORDER BY id
"""

_SELECT_MISSING = """
    SELECT id, discogs_id, NULL AS color
    FROM records
    WHERE discogs_id ~ '^[0-9]+$'
      AND merged_into_id IS NULL
      AND COALESCE(discogs_data->>'vinyl_color_raw', '') = ''
      AND discogs_data->>'vinyl_color_checked_at' IS NULL
    ORDER BY id
    LIMIT :lim
"""

# jsonb_typeof, а не COALESCE: SQLAlchemy кладёт питоновский None в JSONB как
# JSON-null, и `'null'::jsonb || '{"k":"v"}'` даёт МАССИВ [null, {...}], а не
# объект. Та же грабля, что поймана интеграционным тестом в load_release_colors.
_BASE = """
    CASE WHEN jsonb_typeof(discogs_data) = 'object'
         THEN discogs_data ELSE '{}'::jsonb END
"""

_UPDATE_SET = f"""
UPDATE records
   SET discogs_data = ({_BASE}) || jsonb_build_object(
           'vinyl_color_raw', CAST(:color AS text),
           'vinyl_color_checked_at', CAST(:now AS text)),
       updated_at = NOW()
 WHERE id = :id
"""

_UPDATE_CLEAR = f"""
UPDATE records
   SET discogs_data = (({_BASE}) - 'vinyl_color_raw') || jsonb_build_object(
           'vinyl_color_checked_at', CAST(:now AS text)),
       updated_at = NOW()
 WHERE id = :id
"""


def _is_junk(color: str | None) -> bool:
    """Забраковал бы исправленный парсер это сохранённое значение?

    Ровно та функция, что стоит на записи. True = в поле цвета лежит упаковка,
    вес, завод или битрейт.
    """
    return vinyl_color_from_format_texts([color]) is None


async def _candidates(mode: str, limit: int) -> list[dict]:
    async with async_session_maker() as s:
        if mode == "missing":
            rows = (await s.execute(text(_SELECT_MISSING), {"lim": limit})).mappings().all()
            return [dict(r) for r in rows]

        rows = (await s.execute(text(_SELECT_WITH_COLOR))).mappings().all()
    junk = [dict(r) for r in rows if _is_junk(r["color"])]
    return junk[:limit]


async def _fresh_color(discogs_id: str) -> tuple[str | None, bool]:
    """(цвет, успех). Успех=False — сеть/API подвели, запись НЕ трогаем.

    Отличать «Discogs говорит, что цвета нет» от «не доехали» обязательно:
    в первом случае ключ надо снести, во втором — оставить как есть и прийти
    в следующий раз.
    """
    from app.services.cache import cache
    from app.services.discogs import DiscogsService
    from app.services.rate_limiter import Priority

    # В кэше payload, разобранный СТАРЫМ парсером, — без сброса вернётся он же.
    try:
        await cache.delete("release", discogs_id)
    except Exception:  # noqa: BLE001
        logger.debug("cache delete failed for %s", discogs_id, exc_info=True)

    try:
        data = await DiscogsService().get_release(discogs_id, priority=Priority.BATCH)
    except Exception:  # noqa: BLE001
        logger.debug("discogs fetch failed for %s", discogs_id, exc_info=True)
        return None, False

    if not isinstance(data, dict):
        return None, False
    return data.get("vinyl_color_raw"), True


#: Как часто отчитываться о прогрессе. Стояло 100, и при 14 с/запись это были
#: 23 минуты полной тишины в логе — прогон выглядел зависшим, чему я сам и
#: поверил, полез искать труп и чуть не перезапустил живой скрипт. Лог должен
#: доказывать, что работа идёт, чаще, чем раз в получаса.
_PROGRESS_EVERY = 25


def _log_progress(seen: int, total: int, started: float) -> None:
    """Строка прогресса с темпом и остатком времени.

    ETA считаем по факту, а не по теории про 60 rpm: реальный темп зависит от
    того, кто ещё в этот момент ходит в Discogs из того же бакета.
    """
    if seen % _PROGRESS_EVERY and seen != total:
        return
    elapsed = time.monotonic() - started
    per = elapsed / max(seen, 1)
    left = per * (total - seen)
    logger.info(
        "… %d/%d (%.1f с/запись, осталось ~%d мин)",
        seen, total, per, round(left / 60),
    )


async def refetch(mode: str, limit: int, dry_run: bool) -> dict[str, int]:
    counters = {"seen": 0, "fixed": 0, "cleared": 0, "same": 0, "failed": 0}
    rows = await _candidates(mode, limit)
    logger.info("к обработке: %d записей (режим %s)", len(rows), mode)

    started = time.monotonic()

    for row in rows:
        counters["seen"] += 1
        # finally, а не строка в конце тела: у цикла четыре выхода (сбой сети,
        # «не изменилось», dry-run, обычный), и на трёх из них прогресс не
        # печатался бы. Прогон, где всё падает по сети, обязан выглядеть
        # работающим — иначе его опять примут за труп.
        try:
            old = row["color"]
            # Отметку берём на КАЖДУЮ запись, а не один раз на прогон: при
            # трёх часах работы общий штамп врал бы на всю длину прогона, а
            # это единственный след того, когда запись реально проверяли.
            now = datetime.utcnow().isoformat(timespec="seconds")
            new, ok = await _fresh_color(str(row["discogs_id"]))

            if not ok:
                counters["failed"] += 1
                continue
            if new == old:
                counters["same"] += 1
                continue

            if dry_run:
                counters["fixed" if new else "cleared"] += 1
                logger.info("[dry-run] %s: %r -> %r", row["discogs_id"], old, new)
                continue

            async with async_session_maker() as s:
                if new:
                    await s.execute(
                        text(_UPDATE_SET),
                        {"id": row["id"], "color": new, "now": now},
                    )
                    counters["fixed"] += 1
                else:
                    await s.execute(text(_UPDATE_CLEAR), {"id": row["id"], "now": now})
                    counters["cleared"] += 1
                await s.commit()
        finally:
            _log_progress(counters["seen"], len(rows), started)

    logger.info(
        "ГОТОВО: просмотрено=%d цвет_найден=%d мусор_снесён=%d без_изменений=%d ошибок=%d",
        counters["seen"], counters["fixed"], counters["cleared"],
        counters["same"], counters["failed"],
    )
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("junk", "missing"), default="junk")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true", help="ничего не писать")
    args = parser.parse_args()

    if args.mode == "missing" and args.limit > 5000:
        parser.error(
            "--mode missing с лимитом >5000 это часы под лимитом Discogs 60 rpm; "
            "гоняй порциями"
        )

    counters = asyncio.run(refetch(args.mode, args.limit, args.dry_run))
    return 0 if counters["seen"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
