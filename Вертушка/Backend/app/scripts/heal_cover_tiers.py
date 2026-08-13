"""CLI: лечение тиров обложек — замер существующих мастеров + демоут thumb'ов.

Ничего не удаляет. База обложек только накапливается: мелкая картинка остаётся
и на диске, и в БД, но переезжает из канонического слота в плейсхолдерный,
после чего лучший источник получает право её перезаписать.

Два независимых шага (можно гонять по отдельности):

ШАГ 1 `--measure` — проставить `records.cover_min_side` для уже зеркалированных
файлов. До этой правки размер никто не мерил, поэтому NULL стоит у всех ~13K
зеркал, а апгрейд-ветка в `cover_storage.download_and_store` трогает только
строки с известным размером (иначе первый прогрев после деплоя устроил бы
массовую перекачку). Скрипт читает файлы с диска через PIL и заполняет колонку —
после этого мелкие мастера начинают лечиться сами.

ШАГ 2 `--demote` — перенести thumb-grade URL из
`discogs_releases_index.cover_image_url` в `thumb_image_url`. Это разблокирует
офлайн-каналы CAA (`ingest_mb_discogs_map`, `ingest_mb_barcode_covers`): они
пишут ТОЛЬКО в `cover_image_url IS NULL`, а 150px-thumb из версий делал строку
NOT NULL навсегда, из-за чего full-1200 больше не приезжал.

Тир определяется единственным источником правды — `app.services.cover_quality`.
Дублировать разбор размеров regex'ами в SQL нельзя: разойдётся.

ЗАПУСК (на сервере, в контейнере api):
  python -m app.scripts.heal_cover_tiers --measure --demote --dry-run
  python -m app.scripts.heal_cover_tiers --measure --demote --batch 500

Диск: демоут места не занимает. Замер — тоже, но включает апгрейд, и каждая
вылеченная обложка вырастет со ~10 КБ (150px) до ~84 КБ (1000px). Худший случай,
если отравлены все зеркала: +1 ГБ. Поэтому сначала `--dry-run`: он печатает
сколько строк подпадает и сколько это примерно даст прироста.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.services.cover_quality import MASTER_MIN_SIDE, is_thumb_grade

logger = logging.getLogger("heal_cover_tiers")

# Прирост на одну вылеченную обложку: 1000px q85 ≈ 84 КБ против ~10 КБ у 150px.
_UPGRADE_GROWTH_KB = 74


async def measure_existing(batch: int, dry_run: bool) -> tuple[int, int]:
    """Проставить cover_min_side по файлам на диске.

    Возвращает (сколько померено, сколько оказалось ниже порога).
    """
    settings = get_settings()
    covers_dir = Path(settings.covers_dir)
    if not covers_dir.is_dir():
        logger.error("covers dir not found: %s", covers_dir)
        return (0, 0)

    measured = 0
    below = 0
    pending: list[dict] = []

    async with async_session_maker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT discogs_id, cover_local_path FROM records "
                    "WHERE cover_local_path IS NOT NULL "
                    "AND cover_min_side IS NULL "
                    "AND discogs_id IS NOT NULL"
                )
            )
        ).mappings().all()

        logger.info("candidates without cover_min_side: %d", len(rows))

        for row in rows:
            # cover_local_path — 'covers/{id}.jpg' относительно uploads/.
            # covers_dir уже указывает на uploads/covers, поэтому берём basename:
            # склейка 'uploads/covers' + 'covers/x.jpg' дала бы битый путь.
            path = covers_dir / Path(row["cover_local_path"]).name
            if not path.is_file():
                continue
            try:
                with Image.open(path) as img:
                    min_side = min(img.width, img.height)
            except Exception:
                logger.debug("unreadable cover: %s", path, exc_info=True)
                continue

            measured += 1
            if min_side < MASTER_MIN_SIDE:
                below += 1
            pending.append({"did": row["discogs_id"], "ms": min_side})

            if not dry_run and len(pending) >= batch:
                await _flush_sizes(session, pending)
                pending.clear()

        if not dry_run and pending:
            await _flush_sizes(session, pending)

    return (measured, below)


async def _flush_sizes(session, pending: list[dict]) -> None:
    await session.execute(
        text(
            "UPDATE records SET cover_min_side = :ms "
            "WHERE discogs_id = :did AND cover_min_side IS NULL"
        ),
        pending,
    )
    await session.commit()
    logger.info("measured batch: %d rows", len(pending))


async def demote_thumb_urls(batch: int, dry_run: bool) -> int:
    """Перенести thumb-grade cover_image_url в thumb_image_url. Возвращает счёт.

    Keyset-пагинация по discogs_id, а НЕ один SELECT на всю таблицу: строк с
    обложкой в дампе ~1.65 млн, и материализовать их разом в контейнере на 2 ГБ
    рядом с живым API — верный OOM. LIMIT/OFFSET тоже не годится: на глубоких
    смещениях Postgres каждый раз перечитывает префикс.
    """
    moved = 0
    scanned = 0
    last_id = -1
    page = max(batch, 5000)

    async with async_session_maker() as session:
        while True:
            rows = (
                await session.execute(
                    text(
                        "SELECT discogs_id, cover_image_url "
                        "FROM discogs_releases_index "
                        "WHERE cover_image_url IS NOT NULL AND thumb_image_url IS NULL "
                        "AND discogs_id > :last "
                        "ORDER BY discogs_id "
                        "LIMIT :lim"
                    ),
                    {"last": last_id, "lim": page},
                )
            ).mappings().all()
            if not rows:
                break

            scanned += len(rows)
            last_id = rows[-1]["discogs_id"]

            pending = [
                {"did": r["discogs_id"], "url": r["cover_image_url"]}
                for r in rows
                if is_thumb_grade(r["cover_image_url"])
            ]
            moved += len(pending)

            if pending and not dry_run:
                await _flush_demote(session, pending)

            if scanned % 100_000 < page:
                logger.info("demote: scanned %d rows, thumb-grade so far %d", scanned, moved)

    logger.info("demote: scanned %d dump rows total", scanned)
    return moved


async def _flush_demote(session, pending: list[dict]) -> None:
    # Демоут, не удаление: URL переезжает в плейсхолдерный слот, а канонический
    # освобождается под офлайн-CAA (тот пишет только в IS NULL).
    await session.execute(
        text(
            "UPDATE discogs_releases_index "
            "SET thumb_image_url = :url, cover_image_url = NULL "
            "WHERE discogs_id = :did AND cover_image_url = :url"
        ),
        pending,
    )
    await session.commit()
    logger.info("demoted batch: %d rows", len(pending))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", action="store_true", help="шаг 1: замерить существующие мастера")
    parser.add_argument("--demote", action="store_true", help="шаг 2: демоут thumb-grade URL в дампе")
    parser.add_argument("--batch", type=int, default=500, help="размер батча коммита")
    parser.add_argument("--dry-run", action="store_true", help="только посчитать, ничего не писать")
    args = parser.parse_args()

    if not args.measure and not args.demote:
        parser.error("нужен хотя бы один шаг: --measure и/или --demote")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.dry_run:
        logger.info("DRY RUN — ни одной записи в БД не будет")

    if args.measure:
        measured, below = await measure_existing(args.batch, args.dry_run)
        growth_mb = below * _UPGRADE_GROWTH_KB / 1024
        logger.info(
            "measure: %d files sized, %d below %dpx → ожидаемый прирост диска "
            "после перегрева ≈ %.0f МБ",
            measured, below, MASTER_MIN_SIDE, growth_mb,
        )

    if args.demote:
        moved = await demote_thumb_urls(args.batch, args.dry_run)
        logger.info("demote: %d dump rows freed for the offline CAA channel", moved)


if __name__ == "__main__":
    asyncio.run(main())
