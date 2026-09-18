"""Разовая перезаливка обложек skifmusic: миниатюра 270px → оригинал.

Для чего. 18.09.2026 выяснилось, что skifmusic — главный источник мелких
обложек: из 11 099 зеркал мельче 500px 7 224 пришли от него, у 6 777 другого
источника нет. JSON-LD каталога отдаёт миниатюру
`/thumbs/{aa}/{bb}/270x270_1_normal_{hash}.webp`, а у магазина по тому же пути
лежит оригинал с префиксом «x». Парсер исправлен (full_size_image), но уже
сохранённое само не вылечится:

  - адреса в store_listings.raw_payload и discogs_master_covers останутся
    миниатюрами до следующего обхода (мастер — навсегда);
  - файлы обложек записей и мастеров уже лежат 270px, и ничто их не перекачает.

Что делает:
  1. переписывает миниатюры на оригиналы в store_listings.raw_payload.image_url;
  2. то же в discogs_master_covers.cover_image_url (незеркалированные мастера
     дальше подберёт mirror_master_covers_batch уже по новому адресу);
  3. записи с мелкой обложкой и товаром skifmusic — перекачивает оригинал через
     download_and_store: путь апгрейда с полом по cover_min_side, то есть файл
     заменяется ТОЛЬКО если новый крупнее (и на диске, и выселенный в бакет);
  4. уже зеркалированные мастера — то же через _encode_and_place с полом по
     размеру миниатюры из адреса (строки в records у мастера нет).

Идемпотентен: повторный прогон ничего не ухудшит, только доделает недоделанное.
Темп — вежливый к магазину (--pace, по умолчанию 0.3 с).

Usage (внутри scheduler-контейнера):
  python -m app.scripts.upgrade_skifmusic_covers --dry-run
  python -m app.scripts.upgrade_skifmusic_covers [--limit N] [--no-masters]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import datetime

from sqlalchemy import text

from app.database import async_session_maker
from app.services.scrapers.shops.skifmusic import full_size_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("upgrade_skifmusic_covers")

# Тот же шаблон, что в парсере, — для SQL (POSIX-regex Postgres, обратные
# ссылки \1 \2). Меняем только размерный токен, хэш и расширение не трогаем.
_PG_PATTERN = r"(/thumbs/[0-9a-f]{2}/[0-9a-f]{2}/)[0-9x]+(_[0-9]+_normal_[0-9a-f]+\.[a-z]+)$"
_PG_REPL = r"\1x\2"
_THUMB_LIKE = "https://skifmusic.ru/thumbs/%"
_NOT_ORIGINAL = "%/thumbs/__/__/x\\_%"  # уже оригинал — пропускаем

_SIDE_RE = re.compile(r"/thumbs/[0-9a-f]{2}/[0-9a-f]{2}/(\d+)x?(\d+)?_")


def thumb_floor(url: str | None) -> int | None:
    """Меньшая сторона миниатюры по её адресу: «270x270_» → 270, «348x_» → 348.

    Это пол для замены файла мастера: файл скачан с этого адреса, значит он не
    крупнее. Оригинал («x_») пола не даёт — заменять нечего.
    """
    if not url:
        return None
    m = _SIDE_RE.search(url)
    if not m:
        return None
    sides = [int(v) for v in m.groups() if v]
    return min(sides) if sides else None


async def _rewrite_urls(dry_run: bool) -> dict:
    """Шаги 1–2: адреса миниатюр → оригиналы. Батчами, чтобы не держать локи."""
    out = {}
    async with async_session_maker() as db:
        for label, count_sql, update_sql in (
            (
                "listings",
                "SELECT count(*) FROM store_listings WHERE raw_payload->>'image_url' LIKE :like "
                "AND raw_payload->>'image_url' NOT LIKE :orig",
                "UPDATE store_listings SET raw_payload = jsonb_set(raw_payload, '{image_url}', "
                "to_jsonb(regexp_replace(raw_payload->>'image_url', :pat, :repl))) "
                "WHERE id IN (SELECT id FROM store_listings "
                "  WHERE raw_payload->>'image_url' LIKE :like "
                "  AND raw_payload->>'image_url' NOT LIKE :orig LIMIT 2000)",
            ),
            (
                "master_covers",
                "SELECT count(*) FROM discogs_master_covers WHERE cover_image_url LIKE :like "
                "AND cover_image_url NOT LIKE :orig AND mirrored_at IS NULL",
                "UPDATE discogs_master_covers SET cover_image_url = "
                "regexp_replace(cover_image_url, :pat, :repl) "
                "WHERE master_id IN (SELECT master_id FROM discogs_master_covers "
                "  WHERE cover_image_url LIKE :like AND cover_image_url NOT LIKE :orig "
                "  AND mirrored_at IS NULL LIMIT 2000)",
            ),
        ):
            params = {"like": _THUMB_LIKE, "orig": _NOT_ORIGINAL, "pat": _PG_PATTERN, "repl": _PG_REPL}
            total = (await db.execute(text(count_sql), params)).scalar() or 0
            out[label] = {"to_rewrite": total, "rewritten": 0}
            if dry_run or not total:
                continue
            while True:
                res = await db.execute(text(update_sql), params)
                await db.commit()
                if not res.rowcount:
                    break
                out[label]["rewritten"] += res.rowcount
    return out


async def _upgrade_records(dry_run: bool, limit: int | None, pace: float) -> dict:
    """Шаг 3: мелкие обложки записей с товаром skifmusic → оригинал."""
    from app.services.cover_storage import CoverStorageService
    from app.services.cover_demand import TRIGGER_BACKFILL

    async with async_session_maker() as db:
        rows = (await db.execute(text(
            "SELECT DISTINCT ON (r.id) r.discogs_id, r.cover_min_side, "
            "       l.raw_payload->>'image_url' AS image_url "
            "FROM store_listings l "
            "JOIN stores s ON s.id = l.store_id "
            "JOIN records r ON r.id = l.matched_record_id "
            "WHERE s.slug = 'skifmusic' "
            "  AND r.discogs_id ~ '^[0-9]+$' "
            "  AND r.cover_min_side < 500 "
            # Только записи без своего источника: их мелкая обложка почти
            # наверняка и есть миниатюра skifmusic. У остальных (447 на 18.09)
            # свой скан — менять его на фото магазина ради одного размера нельзя.
            "  AND r.cover_image_url IS NULL "
            "  AND l.raw_payload->>'image_url' LIKE :like "
            "ORDER BY r.id, l.last_seen_at DESC "
            + ("LIMIT :lim" if limit else "")
        ), {"like": _THUMB_LIKE, **({"lim": limit} if limit else {})})).all()

    stats = {"candidates": len(rows), "upgraded": 0, "kept": 0, "failed": 0}
    if dry_run:
        for did, side, url in rows[:5]:
            logger.info("  %s (%spx): %s → %s", did, side, url, full_size_image(url))
        return stats

    service = CoverStorageService()
    for i, (did, before, url) in enumerate(rows):
        if i:
            await asyncio.sleep(pace)
        full = full_size_image(url)
        async with async_session_maker() as db:
            try:
                await service.download_and_store(did, full, db, trigger=TRIGGER_BACKFILL)
                after = (await db.execute(
                    text("SELECT cover_min_side FROM records WHERE discogs_id = :d LIMIT 1"),
                    {"d": did},
                )).scalar()
            except Exception:
                logger.warning("запись %s: не вышло", did, exc_info=True)
                stats["failed"] += 1
                continue
        if after is not None and before is not None and after > before:
            stats["upgraded"] += 1
        else:
            stats["kept"] += 1
        if (i + 1) % 200 == 0:
            logger.info("записи: %d/%d, %s", i + 1, len(rows), stats)
    return stats


async def _upgrade_masters(dry_run: bool, pace: float) -> dict:
    """Шаг 4: уже зеркалированные мастера с адресом-миниатюрой → оригинал."""
    from app.services.cover_storage import CoverStorageService, _encode_and_place
    from app.utils.url_guard import safe_image_get

    async with async_session_maker() as db:
        rows = (await db.execute(text(
            "SELECT master_id, cover_image_url FROM discogs_master_covers "
            "WHERE cover_image_url LIKE :like AND cover_image_url NOT LIKE :orig "
            "  AND mirrored_at IS NOT NULL"
        ), {"like": _THUMB_LIKE, "orig": _NOT_ORIGINAL})).all()

    stats = {"candidates": len(rows), "upgraded": 0, "kept": 0, "failed": 0}
    if dry_run:
        return stats

    service = CoverStorageService()
    service._ensure_covers_dir()
    for i, (mid, url) in enumerate(rows):
        if i:
            await asyncio.sleep(pace)
        name = f"m{mid}"
        floor = thumb_floor(url)
        full = full_size_image(url)
        tmp = service._tmp_path(name)
        try:
            resp = await safe_image_get(full, timeout=30)
            resp.raise_for_status()
            placed = await asyncio.to_thread(
                _encode_and_place, resp.content, tmp, service._cover_path(name),
                replace_floor=floor,
            )
        except Exception:
            logger.warning("мастер %s: не вышло", mid, exc_info=True)
            stats["failed"] += 1
            tmp.unlink(missing_ok=True)
            continue
        if not placed.written:
            stats["kept"] += 1
            tmp.unlink(missing_ok=True)
            continue
        stats["upgraded"] += 1
        async with async_session_maker() as db:
            await db.execute(
                text("UPDATE discogs_master_covers SET cover_image_url = :u, mirrored_at = :now "
                     "WHERE master_id = :mid"),
                {"u": full, "now": datetime.utcnow(), "mid": mid},
            )
            await db.commit()
    return stats


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="только для записей")
    ap.add_argument("--no-masters", action="store_true")
    ap.add_argument("--pace", type=float, default=0.3)
    args = ap.parse_args()

    # Порядок важен: мастера апгрейдим ДО переписывания их адресов — нужен
    # размер миниатюры из старого адреса как пол.
    masters = {} if args.no_masters else await _upgrade_masters(args.dry_run, args.pace)
    logger.info("мастера: %s", masters)
    records = await _upgrade_records(args.dry_run, args.limit, args.pace)
    logger.info("записи: %s", records)
    urls = await _rewrite_urls(args.dry_run)
    logger.info("адреса: %s", urls)
    if not args.dry_run:
        from app.services import s3_covers
        logger.info("жду, пока очередь заливки в бакет опустеет…")
        await asyncio.to_thread(s3_covers.wait_uploads_drained)
    logger.info("ГОТОВО%s", " (dry-run, ничего не записано)" if args.dry_run else "")


if __name__ == "__main__":
    asyncio.run(main())
