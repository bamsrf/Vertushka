"""CLI: одноразовый ingest дампа Discogs Releases в локальный индекс.

Что делает:
  - Стримит XML.gz через lxml.iterparse (память константная, ~200 MB).
  - Парсит releases: discogs_id, master_id, artist, title, year, country,
    format_type, label, barcode_norm, catalog_norm, cover_image_url.
  - Записывает батчами (5K строк) через asyncpg.copy_records_to_table — это
    в 10× быстрее INSERT'ов и 100× быстрее single-row INSERT'ов.
  - После завершения вставки строит индексы (CREATE INDEX CONCURRENTLY) —
    btree + GIN trigram. Делать ПОСЛЕ ingest'а — иначе COPY был бы 5-10×
    медленнее (каждая вставка обновляет индексы).

Использование (на проде):

  # 1. Скачать дамп в /data (или другую папку с местом)
  ssh deploy@... 'cd /data && wget https://discogs-data-dumps.s3-us-west-2.amazonaws.com/data/2026/discogs_20260501_releases.xml.gz'

  # 2. Скопировать в контейнер
  ssh deploy@... 'docker cp /data/discogs_20260501_releases.xml.gz vertushka_api:/tmp/'

  # 3. Применить миграцию (создаст таблицу)
  ssh deploy@... 'docker exec vertushka_api alembic upgrade head'

  # 4. Запустить ingest (в фоне, ~3-5 часов)
  ssh deploy@... 'docker exec -d vertushka_api python -m app.scripts.ingest_discogs_dump \
    --file /tmp/discogs_20260501_releases.xml.gz \
    --dump-date 2026-05-01 \
    > /tmp/ingest.log 2>&1'

  # 5. Мониторить прогресс
  ssh deploy@... 'docker exec vertushka_api tail -f /tmp/ingest.log'

  # 6. Только индексы (если нужно пересоздать)
  ssh deploy@... 'docker exec vertushka_api python -m app.scripts.ingest_discogs_dump --build-indexes-only'

  # 7. Удалить XML после успеха
  ssh deploy@... 'docker exec vertushka_api rm /tmp/discogs_20260501_releases.xml.gz'

Параметры:
  --file PATH            путь к XML.gz дампу
  --dump-date YYYY-MM-DD дата дампа (для dump_version)
  --batch-size N         кол-во записей в одном COPY-батче (default: 5000)
  --limit N              максимум обработанных записей (для тестов)
  --resume-from ID       продолжить после данного discogs_id
  --build-indexes-only   пропустить ingest, только создать индексы
  --skip-existing        не падать при ON CONFLICT (Update mode)

Идемпотентность: повторный запуск с --skip-existing проходит без ошибок
(использует upsert через staging table). Без флага падает на дубликатах PK.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from app.database import async_session_maker, engine, close_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest_discogs_dump")


# ────────────────────────────────────────────────────────────────────────
# Нормализация — те же правила что в listing_matcher для совместимости
# ────────────────────────────────────────────────────────────────────────


_BARCODE_RE = re.compile(r"\D+")  # всё что не цифра
_CATALOG_RE = re.compile(r"[\s\-\.]+")


def _norm_barcode(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = _BARCODE_RE.sub("", raw).strip()
    return cleaned or None


def _norm_catalog(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = _CATALOG_RE.sub("", raw).upper().strip()
    return cleaned or None


# ────────────────────────────────────────────────────────────────────────
# XML parsing — lxml iterparse-friendly хелперы
# ────────────────────────────────────────────────────────────────────────


def _xpath_text(elem, path: str) -> str | None:
    """Возвращает .text первого элемента по xpath, или None."""
    found = elem.find(path)
    if found is None:
        return None
    text = found.text
    return text.strip() if text else None


def _xpath_int(elem, path: str) -> int | None:
    text = _xpath_text(elem, path)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _xpath_attr(elem, path: str, attr: str) -> str | None:
    found = elem.find(path)
    if found is None:
        return None
    val = found.get(attr)
    return val.strip() if val else None


def _parse_year(elem) -> int | None:
    """`<released>2024-03-15</released>` или просто `<released>2024</released>`."""
    text = _xpath_text(elem, "released")
    if not text:
        return None
    # Берём первые 4 цифры
    m = re.match(r"\d{4}", text)
    if not m:
        return None
    try:
        y = int(m.group())
        # Дамп иногда содержит явно невалидные годы (0, 9999) — фильтруем
        if 1900 <= y <= 2100:
            return y
    except ValueError:
        pass
    return None


def _derive_format(elem) -> str | None:
    """`<formats><format name="Vinyl" qty="2"><descriptions><description>LP`.

    Возвращает короткую строку типа "Vinyl, LP" или "CD" — для отображения
    и быстрого фильтра в matcher'е.
    """
    fmt = elem.find(".//formats/format")
    if fmt is None:
        return None
    name = fmt.get("name") or ""
    descriptions = [d.text for d in fmt.findall("descriptions/description") if d.text]
    if descriptions:
        return f"{name}, {descriptions[0]}".strip(", ")
    return name or None


def _norm_barcode_from_identifiers(elem) -> str | None:
    """`<identifiers><identifier type="Barcode" value="..."`. Берём первый."""
    for ident in elem.findall(".//identifiers/identifier"):
        if ident.get("type") == "Barcode":
            return _norm_barcode(ident.get("value"))
    return None


def _catalog_from_labels(elem) -> str | None:
    """Из `<labels><label catno="..."` — берём первый non-empty."""
    for label in elem.findall(".//labels/label"):
        catno = label.get("catno")
        normalized = _norm_catalog(catno)
        if normalized:
            return normalized
    return None


def _first_label_name(elem) -> str | None:
    for label in elem.findall(".//labels/label"):
        name = label.get("name")
        if name:
            return name.strip()
    return None


def _parse_release(elem, dump_date: date) -> dict[str, Any] | None:
    """Парсит один <release>. Возвращает dict для COPY или None если skip.

    NB: с 2025 г. Discogs убрали атрибут status="Accepted" из дампов —
    раньше отсеивали через него Draft/Rejected, теперь принимаем все
    записи. Если в будущем появится — добавить обратно как allowlist.
    """
    discogs_id_attr = elem.get("id")
    if not discogs_id_attr:
        return None
    try:
        discogs_id = int(discogs_id_attr)
    except ValueError:
        return None

    artist = _xpath_text(elem, ".//artists/artist/name")
    title = _xpath_text(elem, "title")
    if not artist or not title:
        return None

    return {
        "discogs_id": discogs_id,
        # Discogs пишет <master_id>0</master_id> у релизов без мастера —
        # 0 это НЕ id, храним NULL (release-only семантика в artist-grid и др.)
        "master_id": _xpath_int(elem, "master_id") or None,
        "artist": artist,
        "title": title,
        "year": _parse_year(elem),
        "country": _xpath_text(elem, "country"),
        "format_type": _derive_format(elem),
        "label": _first_label_name(elem),
        "barcode_norm": _norm_barcode_from_identifiers(elem),
        "catalog_norm": _catalog_from_labels(elem),
        "cover_image_url": None,  # dump has 0 cover URLs (verified 0/13.1M on prod) — column kept for schema stability
        "dump_version": dump_date,
        "created_at": datetime.utcnow(),
    }


# ────────────────────────────────────────────────────────────────────────
# COPY через asyncpg (через raw connection из SQLAlchemy)
# ────────────────────────────────────────────────────────────────────────


_COLUMNS = (
    "discogs_id", "master_id", "artist", "title", "year", "country",
    "format_type", "label", "barcode_norm", "catalog_norm",
    "cover_image_url", "dump_version", "created_at",
)


async def _copy_batch(records: list[dict], skip_existing: bool) -> int:
    """Bulk-insert через asyncpg COPY. Возвращает кол-во вставленных строк.

    При skip_existing=True использует staging table + INSERT ... ON CONFLICT —
    медленнее, но не падает на дубликатах. Без флага — прямой COPY (быстрее),
    но падает с UniqueViolation на повторных запусках.
    """
    if not records:
        return 0

    tuples = [
        (
            r["discogs_id"], r["master_id"], r["artist"], r["title"],
            r["year"], r["country"], r["format_type"], r["label"],
            r["barcode_norm"], r["catalog_norm"], r["cover_image_url"],
            r["dump_version"], r["created_at"],
        )
        for r in records
    ]

    async with engine.connect() as conn:
        raw_conn = await conn.get_raw_connection()
        asyncpg_conn = raw_conn.driver_connection  # asyncpg.Connection

        if skip_existing:
            # Staging table → INSERT ON CONFLICT — медленнее, но безопасно
            # для повторных запусков.
            await asyncpg_conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS _stage "
                "(LIKE discogs_releases_index INCLUDING DEFAULTS) ON COMMIT DELETE ROWS"
            )
            await asyncpg_conn.copy_records_to_table(
                "_stage", records=tuples, columns=_COLUMNS,
            )
            inserted = await asyncpg_conn.fetchval(
                "WITH ins AS ("
                " INSERT INTO discogs_releases_index "
                f" ({', '.join(_COLUMNS)}) "
                f" SELECT {', '.join(_COLUMNS)} FROM _stage "
                " ON CONFLICT (discogs_id) DO NOTHING "
                " RETURNING 1"
                ") SELECT COUNT(*) FROM ins"
            )
            return int(inserted or 0)
        else:
            await asyncpg_conn.copy_records_to_table(
                "discogs_releases_index", records=tuples, columns=_COLUMNS,
            )
            return len(tuples)


# ────────────────────────────────────────────────────────────────────────
# Main ingest loop
# ────────────────────────────────────────────────────────────────────────


async def ingest(
    file_path: Path,
    dump_date: date,
    batch_size: int,
    limit: int | None,
    resume_from: int | None,
    skip_existing: bool,
) -> dict[str, int]:
    counters = {"parsed": 0, "skipped": 0, "inserted": 0, "errors": 0}
    batch: list[dict] = []
    started = time.time()
    last_report = started
    resuming = resume_from is not None

    logger.info(
        "Starting ingest: file=%s, dump_date=%s, batch=%d, limit=%s, resume=%s, skip_existing=%s",
        file_path, dump_date, batch_size, limit, resume_from, skip_existing,
    )

    with gzip.open(file_path, "rb") as f:
        # iterparse — streaming SAX-like, память константная.
        # tag="release" — событие только когда `</release>` закрывается.
        for event, elem in etree.iterparse(f, tag="release"):
            try:
                row = _parse_release(elem, dump_date)
                if row is None:
                    counters["skipped"] += 1
                else:
                    # Resume-режим: пропускаем до встречи resume_from
                    if resuming:
                        if row["discogs_id"] <= resume_from:
                            counters["skipped"] += 1
                            elem.clear()
                            continue
                        resuming = False
                        logger.info("Resume done — picking up at discogs_id=%d", row["discogs_id"])

                    batch.append(row)
                    counters["parsed"] += 1

                    if len(batch) >= batch_size:
                        try:
                            inserted = await _copy_batch(batch, skip_existing)
                            counters["inserted"] += inserted
                        except Exception:
                            counters["errors"] += 1
                            logger.exception("batch failed at parsed=%d", counters["parsed"])
                        batch = []

                # Прогресс каждые 30 секунд.
                now = time.time()
                if now - last_report >= 30:
                    rate = counters["parsed"] / (now - started)
                    logger.info(
                        "progress: parsed=%d inserted=%d skipped=%d errors=%d rate=%.0f/s",
                        counters["parsed"], counters["inserted"],
                        counters["skipped"], counters["errors"], rate,
                    )
                    last_report = now

                if limit and counters["parsed"] >= limit:
                    logger.info("Limit %d reached, stopping", limit)
                    break

            finally:
                # КРИТИЧНО: освобождаем memory элемента после обработки.
                # Без этого lxml держит всё дерево в памяти.
                elem.clear()
                # Также чистим предков, чтобы освободить буфер lxml целиком.
                while elem.getprevious() is not None:
                    del elem.getparent()[0]

    # Финальный batch
    if batch:
        try:
            inserted = await _copy_batch(batch, skip_existing)
            counters["inserted"] += inserted
        except Exception:
            counters["errors"] += 1
            logger.exception("final batch failed")

    elapsed = time.time() - started
    logger.info(
        "Ingest done in %.1fs: %s | rate=%.0f rows/s",
        elapsed, counters, counters["parsed"] / max(elapsed, 1),
    )
    return counters


# ────────────────────────────────────────────────────────────────────────
# Index building (CREATE INDEX CONCURRENTLY)
# ────────────────────────────────────────────────────────────────────────


# Названия + DDL индексов. CONCURRENTLY — не блокирует таблицу, но требует
# autocommit (не работает в транзакции).
_INDEXES = [
    (
        "ix_dri_barcode",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dri_barcode "
        "ON discogs_releases_index (barcode_norm) WHERE barcode_norm IS NOT NULL",
    ),
    (
        "ix_dri_catalog",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dri_catalog "
        "ON discogs_releases_index (catalog_norm) WHERE catalog_norm IS NOT NULL",
    ),
    (
        "ix_dri_master_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dri_master_id "
        "ON discogs_releases_index (master_id) WHERE master_id IS NOT NULL",
    ),
    (
        "ix_dri_artist_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dri_artist_trgm "
        "ON discogs_releases_index USING GIN (artist gin_trgm_ops)",
    ),
    (
        "ix_dri_title_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_dri_title_trgm "
        "ON discogs_releases_index USING GIN (title gin_trgm_ops)",
    ),
]


async def build_indexes() -> None:
    """Создаёт btree + GIN trigram индексы. Каждый — отдельным CONCURRENTLY."""
    logger.info("Building indexes (each CONCURRENTLY)...")
    # Проверяем pg_trgm extension — без неё GIN trigram не создастся.
    async with engine.connect() as conn:
        raw_conn = await conn.get_raw_connection()
        asyncpg_conn = raw_conn.driver_connection
        await asyncpg_conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for name, ddl in _INDEXES:
            started = time.time()
            logger.info("  → %s", name)
            try:
                # CONCURRENTLY требует autocommit; asyncpg по умолчанию вне транзакции.
                await asyncpg_conn.execute(ddl)
                logger.info("  ✓ %s built in %.1fs", name, time.time() - started)
            except Exception:
                logger.exception("  ✗ %s failed", name)


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, help="Путь к XML.gz дампу")
    parser.add_argument("--dump-date", type=str, help="Дата дампа YYYY-MM-DD")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Ограничить кол-во обработанных записей")
    parser.add_argument("--resume-from", type=int, default=None, help="Продолжить после discogs_id")
    parser.add_argument("--skip-existing", action="store_true", help="ON CONFLICT DO NOTHING")
    parser.add_argument("--build-indexes-only", action="store_true", help="Только создать индексы")
    args = parser.parse_args()

    if args.build_indexes_only:
        await build_indexes()
        await close_db()
        return

    if not args.file or not args.dump_date:
        parser.error("--file и --dump-date обязательны для ingest")

    if not args.file.exists():
        parser.error(f"Файл не найден: {args.file}")

    dump_date = datetime.strptime(args.dump_date, "%Y-%m-%d").date()

    counters = await ingest(
        file_path=args.file,
        dump_date=dump_date,
        batch_size=args.batch_size,
        limit=args.limit,
        resume_from=args.resume_from,
        skip_existing=args.skip_existing,
    )

    logger.info("Final counters: %s", counters)

    # Автоматически строим индексы после успешного ingest'а.
    if counters["inserted"] > 0 and counters["errors"] == 0:
        await build_indexes()

    await close_db()


if __name__ == "__main__":
    asyncio.run(_main())
