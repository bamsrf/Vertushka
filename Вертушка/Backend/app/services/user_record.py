"""
User-submitted records (source='user') — дабл-чек и создание.

preflight_dedup — ядро фичи: перед созданием user-record прогоняем каскад, чтобы
не плодить дубли того, что уже есть в Маркете/Discogs. Переиспользуем готовые
кирпичи listing_matcher (barcode/catalog/fuzzy/dump-index) + normalize из
scrapers.extractors. См. docs/plans/collection/USER_SUBMITTED_RECORDS.md §2.

Каскад:
    1. barcode  → exact в records           → DUPLICATE
    2. catalog  → norm в records             → DUPLICATE
    3. fuzzy(artist+title+year) в records    → LIKELY_DUPLICATE (score ≥ thr)
    4. Discogs: dump-index (оффлайн) или live → FOUND_IN_DISCOGS
       (у обеих веток свой порог схожести — Discogs search fuzzy и на мусорный
        запрос возвращает популярный релиз; top-1 без проверки брать нельзя)
    5. чисто                                  → ALLOW_CREATE
"""
import logging
import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import Record
from app.services.discogs import DiscogsService
from app.services.listing_matcher import (
    FORMAT_MISMATCH_PENALTY,
    _find_by_barcode,
    _find_by_catalog,
    _format_family,
    _fuzzy_candidates,
    _is_dump_available,
    _lookup_in_dump_index,
)
from app.services.scrapers.extractors import normalize_barcode, normalize_catalog

logger = logging.getLogger(__name__)


# Порог fuzzy на шкале 0..1 (title*0.6 + artist*0.3 + year-bonus 0.1), как у
# listing_matcher._fuzzy_score. Мягче store-порога (0.85), т.к. тут human-in-loop:
# юзер подтверждает «да, это она» или настаивает на создании.
LIKELY_DUPLICATE_THRESHOLD = 0.72

# Порог для кандидата из live-поиска Discogs. Жёстче, чем LIKELY_DUPLICATE:
# Discogs search сам по себе fuzzy и на мусорный запрос всегда возвращает
# что-нибудь популярное. Без порога top-1 объявлялся дублем и юзер добавлял
# в коллекцию случайный релиз.
# 0.78 = точное название + артист, узнаваемый на ~0.6 (у Discogs это «Cher (2)»,
# «Various» и прочие суффиксы). Мусорные топы дают 0.1–0.3 — запас огромный.
# Ошибку в эту сторону чинит сам юзер: он видит кандидата и жмёт «всё равно
# создать своё».
DISCOGS_LIVE_MATCH_THRESHOLD = 0.78


class PreflightStatus:
    DUPLICATE = "DUPLICATE"            # точный матч (barcode/catalog) в records
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE"  # fuzzy-матч в records
    FOUND_IN_DISCOGS = "FOUND_IN_DISCOGS"  # есть в Discogs → обычный флоу
    ALLOW_CREATE = "ALLOW_CREATE"     # чисто, пускаем в форму


@dataclass
class DiscogsCandidate:
    """Найденный в Discogs релиз — с метаданными, чтобы фронт показал юзеру,
    ЧТО именно он собирается добавить (иначе кнопка жмётся вслепую)."""
    discogs_id: str
    artist: str | None = None
    title: str | None = None
    year: int | None = None
    cover_image_url: str | None = None


@dataclass
class PreflightResult:
    status: str
    # Для DUPLICATE/LIKELY_DUPLICATE — найденный Record (наш).
    match: Record | None = None
    # Для FOUND_IN_DISCOGS — discogs_id, чтобы фронт ушёл в Discogs-флоу.
    discogs_id: str | None = None
    # Для FOUND_IN_DISCOGS — метаданные найденного (превью на экране-перехвате).
    discogs_match: DiscogsCandidate | None = None
    score: float | None = None


def _fuzzy_score_fields(
    *,
    cand_artist: str | None,
    cand_title: str | None,
    cand_year: int | None,
    cand_format: str | None,
    artist: str | None,
    title: str | None,
    year: int | None,
    format_type: str | None,
) -> float:
    """0..1 score по user-payload (без StoreListing). Зеркалит _fuzzy_score."""
    title_score = fuzz.token_sort_ratio(cand_title or "", title or "") / 100.0
    artist_score = (
        fuzz.token_sort_ratio(cand_artist or "", artist or "") / 100.0
        if artist else 0.5
    )
    year_bonus = 0.1 if (cand_year and year and cand_year == year) else 0.0
    score = min(1.0, title_score * 0.6 + artist_score * 0.3 + year_bonus)
    # Format-aware (§9): известные и различные носители (винил-ввод → CD-релиз)
    # давим ниже порога, чтобы fuzzy не путал форматы. Как в _fuzzy_score.
    uf, rf = _format_family(format_type), _format_family(cand_format)
    if uf and rf and uf != rf:
        score *= FORMAT_MISMATCH_PENALTY
    return score


def _preflight_fuzzy_score(
    rec: Record,
    artist: str | None,
    title: str | None,
    year: int | None,
    format_type: str | None = None,
) -> float:
    """Обёртка над _fuzzy_score_fields для нашего Record."""
    return _fuzzy_score_fields(
        cand_artist=rec.artist,
        cand_title=rec.title,
        cand_year=rec.year,
        cand_format=rec.format_type,
        artist=artist,
        title=title,
        year=year,
        format_type=format_type,
    )


async def preflight_dedup(
    *,
    artist: str,
    title: str,
    year: int | None = None,
    barcode: str | None = None,
    catalog: str | None = None,
    format_type: str | None = None,
    db: AsyncSession,
    check_discogs: bool = True,
) -> PreflightResult:
    """Дабл-чек перед созданием user-record. Не делает commit."""
    # 1) barcode exact
    bc = normalize_barcode(barcode)
    if bc:
        rec = await _find_by_barcode(db, bc)
        if rec is not None:
            return PreflightResult(PreflightStatus.DUPLICATE, match=rec, score=1.0)

    # 2) catalog norm
    cat = normalize_catalog(catalog)
    if cat:
        rec = await _find_by_catalog(db, cat)
        if rec is not None:
            return PreflightResult(PreflightStatus.DUPLICATE, match=rec, score=0.9)

    # 3) fuzzy(artist+title+year) против records (любой source)
    candidates = await _fuzzy_candidates(db, artist, title)
    best, best_score = None, 0.0
    for rec in candidates:
        s = _preflight_fuzzy_score(rec, artist, title, year, format_type)
        if s > best_score:
            best, best_score = rec, s
    if best is not None and best_score >= LIKELY_DUPLICATE_THRESHOLD:
        return PreflightResult(
            PreflightStatus.LIKELY_DUPLICATE, match=best, score=round(best_score, 3)
        )

    # 4) Discogs check
    if check_discogs:
        cand = await _check_discogs(
            db,
            artist=artist,
            title=title,
            year=year,
            barcode=bc,
            catalog=cat,
            format_type=format_type,
        )
        if cand:
            return PreflightResult(
                PreflightStatus.FOUND_IN_DISCOGS,
                discogs_id=cand.discogs_id,
                discogs_match=cand,
            )

    # 5) чисто
    return PreflightResult(PreflightStatus.ALLOW_CREATE)


async def _check_discogs(
    db: AsyncSession,
    *,
    artist: str,
    title: str,
    year: int | None,
    barcode: str | None,
    catalog: str | None,
    format_type: str | None = None,
) -> DiscogsCandidate | None:
    """Discogs-проверка: сначала оффлайн dump-индекс, при промахе — live API.

    Дамп устаревает: свежий релиз в нём может отсутствовать, хотя в живом Discogs
    он есть. Поэтому при промахе дампа ВСЁ РАВНО проверяем live — иначе плодим
    лишние user-records на релизы, которые на самом деле в Discogs есть.
    """
    # a) dump-индекс (быстро, оффлайн). Пороги схожести — внутри lookup'а.
    if await _is_dump_available(db):
        hit = await _lookup_in_dump_index(
            db,
            barcode=barcode,
            catalog=catalog,
            artist=artist,
            title=title,
            year=year,
            listing_format=format_type,
        )
        if hit is not None:
            row, _method, _conf = hit
            if row.get("discogs_id"):
                return DiscogsCandidate(
                    discogs_id=str(row["discogs_id"]),
                    artist=row.get("artist"),
                    title=row.get("title"),
                    year=row.get("year"),
                    cover_image_url=row.get("cover_image_url"),
                )
            return None
        # промах дампа → проваливаемся в live (свежие/нишевые релизы)

    # b) live Discogs search (дамп не залит ИЛИ промах дампа).
    # Discogs search — fuzzy: на мусорный запрос он всё равно вернёт что-то
    # популярное. Поэтому каждого кандидата гоняем через тот же fuzzy-score,
    # что и записи из нашей БД, и берём лучшего только выше порога.
    try:
        svc = DiscogsService()
        query = f"{artist} {title}".strip()
        resp = await svc.search(query=query, artist=artist or None, year=year, per_page=5)
        best, best_score = None, 0.0
        for r in (resp.results if resp else []):
            if not getattr(r, "discogs_id", None):
                continue
            s = _fuzzy_score_fields(
                cand_artist=r.artist,
                cand_title=r.title,
                cand_year=r.year,
                cand_format=r.format_type,
                artist=artist,
                title=title,
                year=year,
                format_type=format_type,
            )
            if s > best_score:
                best, best_score = r, s
        if best is not None and best_score >= DISCOGS_LIVE_MATCH_THRESHOLD:
            return DiscogsCandidate(
                discogs_id=str(best.discogs_id),
                artist=best.artist,
                title=best.title,
                year=best.year,
                cover_image_url=best.cover_image_url or best.thumb_image_url,
            )
        if best is not None:
            logger.info(
                "preflight: discogs top candidate rejected (score %.3f < %.2f) for %r",
                best_score, DISCOGS_LIVE_MATCH_THRESHOLD, query,
            )
    except Exception as e:  # noqa: BLE001 — live discogs не должен ронять preflight
        logger.warning("preflight live discogs check failed: %s", e)
    return None


async def create_user_record(
    *,
    db: AsyncSession,
    created_by_user_id: uuid.UUID,
    artist: str,
    title: str,
    year: int | None = None,
    label: str | None = None,
    catalog_number: str | None = None,
    country: str | None = None,
    format_type: str | None = None,
    barcode: str | None = None,
    tracklist: list | None = None,
    cover_image_url: str | None = None,
    spotify_album_id: str | None = None,
    user_submitted_data: dict | None = None,
) -> Record:
    """Создать source='user' запись. Модерация отменена (§6) — сразу approved.

    Запись сразу видна всем и растёт в коллекцию создателя. Дедуп (preflight)
    отсекает дубли до создания; ручной модерации/админки нет.
    """
    rec = Record(
        source="user",
        created_by_user_id=created_by_user_id,
        moderation_status="approved",
        artist=artist,
        title=title,
        year=year,
        label=label,
        catalog_number=catalog_number,
        country=country,
        format_type=format_type,
        barcode=normalize_barcode(barcode) or barcode,
        tracklist=tracklist,
        cover_image_url=cover_image_url,
        spotify_album_id=spotify_album_id,
        user_submitted_data=user_submitted_data,
    )
    db.add(rec)
    await db.flush()
    return rec


# Поля, которые автор может править у своей user-record (§11).
_EDITABLE_FIELDS = (
    "artist",
    "title",
    "year",
    "label",
    "catalog_number",
    "country",
    "format_type",
    "tracklist",
)


async def update_user_record(
    *,
    db: AsyncSession,
    record: Record,
    changes: dict,
) -> Record:
    """Применить правки автора к его user-record. Не делает commit.

    Guard (source/owner) проверяет вызывающий код. Здесь — только применение
    разрешённых полей из `changes` (None-значения пропускаем, кроме явного
    сброса не делаем). Barcode нормализуем, если пришёл.
    """
    for field in _EDITABLE_FIELDS:
        if field in changes and changes[field] is not None:
            setattr(record, field, changes[field])
    if changes.get("barcode") is not None:
        record.barcode = normalize_barcode(changes["barcode"]) or changes["barcode"]
    await db.flush()
    return record


# Мягкое удаление: запись не стирается из БД, а уходит в 'deleted'. Физический
# DELETE опасен — на record_id висят коллекции, вишлисты, подарки, клики по
# офферам и ачивки; каскад либо порвал бы их, либо выпилил чужую историю.
DELETED_STATUS = "deleted"


async def count_foreign_holders(
    *, db: AsyncSession, record: Record, owner_id: uuid.UUID
) -> int:
    """Сколько ЧУЖИХ людей держат эту запись в коллекции или вишлисте.

    Правило владельца: свою ручную запись можно убрать, только пока она никому
    больше не понадобилась. Как только чужая коллекция на неё сослалась, запись
    перестаёт быть личной черновой — удаление сломало бы её у других людей.
    """
    from sqlalchemy import func, select

    from app.models.collection import Collection, CollectionItem
    from app.models.wishlist import Wishlist, WishlistItem

    in_collections = await db.scalar(
        select(func.count(func.distinct(Collection.user_id)))
        .select_from(CollectionItem)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(CollectionItem.record_id == record.id, Collection.user_id != owner_id)
    ) or 0
    in_wishlists = await db.scalar(
        select(func.count(func.distinct(Wishlist.user_id)))
        .select_from(WishlistItem)
        .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
        .where(WishlistItem.record_id == record.id, Wishlist.user_id != owner_id)
    ) or 0
    return int(in_collections) + int(in_wishlists)


async def soft_delete_user_record(
    *, db: AsyncSession, record: Record, owner_id: uuid.UUID
) -> None:
    """Пометить запись удалённой и отцепить её от коллекции/вишлиста автора.

    Свои ссылки чистим: иначе в коллекции осталась бы карточка, которая по
    тапу отдаёт 404. Не делает commit — вызывающий код коммитит сам.
    """
    from sqlalchemy import delete, select

    from app.models.collection import Collection, CollectionItem
    from app.models.wishlist import Wishlist, WishlistItem

    record.moderation_status = DELETED_STATUS

    own_collections = select(Collection.id).where(Collection.user_id == owner_id)
    await db.execute(
        delete(CollectionItem).where(
            CollectionItem.record_id == record.id,
            CollectionItem.collection_id.in_(own_collections),
        )
    )
    own_wishlists = select(Wishlist.id).where(Wishlist.user_id == owner_id)
    await db.execute(
        delete(WishlistItem).where(
            WishlistItem.record_id == record.id,
            WishlistItem.wishlist_id.in_(own_wishlists),
        )
    )
    await db.flush()
