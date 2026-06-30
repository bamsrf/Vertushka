"""Дозапись одиночных Discogs-релизов в discogs_releases_index (search-индекс).

Обычно индекс наполняется батч-ингестом дампа (scripts/ingest_discogs_dump.py).
Но дамп устаревает — свежие релизы, добытые из live Discogs API, в нём
отсутствуют. Этот helper кладёт такой релиз в индекс «на лету», чтобы
`/records/search` нашёл его в следующий раз. См. docs/plans/USER_SUBMITTED_RECORDS
и план Discogs-first.

Единая точка вызова — api/records.py::get_or_create_record_by_discogs_id: любой
впервые открытый/добавленный Discogs-релиз обогащает индекс.
"""
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scrapers.extractors import normalize_barcode, normalize_catalog

logger = logging.getLogger(__name__)


async def filter_artist_names_with_releases(
    db: AsyncSession, names: list[str]
) -> set[str]:
    """Из списка имён артистов вернуть множество (lower-cased) тех, у кого в
    локальном дамп-индексе есть хоть один релиз — по производной таблице
    discogs_artist_names (btree PK, index-scan, без вызовов Discogs).

    Жёсткий фильтр выдачи поиска: имя не вернулось → у артиста нет релизов в
    дампе → дроп. Fail-open: при ошибке БД возвращаем все имена (поиск не
    деградирует), вызывающий тогда никого не дропает.
    """
    norm = {n.strip().lower() for n in names if n and n.strip()}
    if not norm:
        return set()
    try:
        rows = await db.execute(
            text(
                "SELECT name_norm FROM discogs_artist_names "
                "WHERE name_norm = ANY(:names)"
            ),
            {"names": list(norm)},
        )
        return {r[0] for r in rows}
    except Exception as e:  # noqa: BLE001 — fail-open, не роняем поиск
        logger.warning("filter_artist_names_with_releases failed: %s", e)
        return norm  # все «прошли» → дропа не будет


def _to_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


async def upsert_release_into_index(db: AsyncSession, record_data: dict) -> None:
    """Положить один Discogs-релиз в discogs_releases_index. Идемпотентно.

    record_data — dict из DiscogsService.get_release (ключи id/master_id/artist/
    title/year/country/format/label/barcode/catalog_number/cover_image).
    Ошибки глотаем (обогащение индекса не должно ронять основной флоу).
    """
    discogs_id = _to_int(record_data.get("id"))
    if discogs_id is None:
        return
    artist = (record_data.get("artist") or "").strip()
    title = (record_data.get("title") or "").strip()
    if not artist or not title:
        return  # artist/title NOT NULL в схеме

    params = {
        "discogs_id": discogs_id,
        "master_id": _to_int(record_data.get("master_id")),
        "artist": artist,
        "title": title,
        "year": _to_int(record_data.get("year")),
        "country": record_data.get("country"),
        "format_type": record_data.get("format"),
        "label": record_data.get("label"),
        "barcode_norm": normalize_barcode(record_data.get("barcode")),
        "catalog_norm": normalize_catalog(record_data.get("catalog_number")),
        "cover_image_url": record_data.get("cover_image"),
        "dump_version": date.today(),
    }
    try:
        await db.execute(
            text(
                "INSERT INTO discogs_releases_index "
                "(discogs_id, master_id, artist, title, year, country, "
                " format_type, label, barcode_norm, catalog_norm, "
                " cover_image_url, dump_version) "
                "VALUES (:discogs_id, :master_id, :artist, :title, :year, "
                " :country, :format_type, :label, :barcode_norm, :catalog_norm, "
                " :cover_image_url, :dump_version) "
                "ON CONFLICT (discogs_id) DO NOTHING"
            ),
            params,
        )
        # Держим производную таблицу имён в синхроне, чтобы свежий live-артист
        # сразу проходил фильтр поиска (см. filter_artist_names_with_releases).
        await db.execute(
            text(
                "INSERT INTO discogs_artist_names (name_norm) VALUES (:name) "
                "ON CONFLICT (name_norm) DO NOTHING"
            ),
            {"name": artist.lower()},
        )
    except Exception as e:  # noqa: BLE001 — индекс-обогащение не критично
        logger.warning("upsert_release_into_index failed for %s: %s", discogs_id, e)
