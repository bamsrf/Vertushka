"""
Матчинг листингов магазинов с записями (Record).

Стратегия — каскад фолбэков с разными confidence:
  1. discogs_release_url (raw_payload) → точное совпадение по Record.discogs_id  → 1.0
  2. barcode → Record.barcode                                                     → 1.0
  3. catalog_number → Record.catalog_number (нормализованный)                     → 0.9
  4. fuzzy(artist + title + year) через pg_trgm + rapidfuzz                       → score
  5. on-demand fetch через Discogs (если есть barcode/catalog но Record нет)      → 0.95
  6. store-native fallback: если Discogs ничего не знает — создаём Record из     → 1.0
     данных листинга (source='store', discogs_id=NULL). Только при выполнении
     anti-noise gate (см. _should_create_store_native).

Пишет: matched_record_id, match_confidence, match_method, matched_at.
Не падает на единичных ошибках — собирает счётчики, логирует.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable

import re

from rapidfuzz import fuzz
from sqlalchemy import select, text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.record import Record
from app.models.store_listing import StoreListing, MatchMethod
from app.services.scrapers.extractors import (
    normalize_barcode,
    normalize_catalog,
    infer_format,
    barcode_variants,
)
from app.services.vinyl_color import color_family

logger = logging.getLogger(__name__)


FUZZY_THRESHOLD = 0.85
FUZZY_CANDIDATES_LIMIT = 50

# Штраф fuzzy-score при конфликте носителя (винил-листинг ↔ CD-релиз и т.п.).
# 1.0 * 0.3 = 0.3 < FUZZY_THRESHOLD → конфликтный кандидат отсекается.
FORMAT_MISMATCH_PENALTY = 0.3

# Штраф fuzzy-score при конфликте семьи цвета винила (чёрный листинг ↔ зелёный
# релиз и т.п.). §A WS-A1: fuzzy опознаёт альбом, не пресс — без штрафа чёрный
# In Utero липнет к зелёной записи. Применяем ТОЛЬКО когда обе семьи известны
# (см. vinyl_color.color_family) — отсутствие цвета не штрафуем. 0.3 симметрично
# FORMAT_MISMATCH_PENALTY: уводит кандидата ниже FUZZY_THRESHOLD.
COLOR_MISMATCH_PENALTY = 0.3


def _format_family(raw: str | None) -> str | None:
    """Грубая «семья носителя» для сравнения форматов листинга и записи.

    Прогоняем через infer_format (понимает Vinyl/LP/CD/Cassette в любом
    написании), затем сворачиваем в семью. Box Set / неизвестное → None
    (penalty не применяется — бокс бывает и виниловый, и CD).
    """
    fmt = infer_format(raw)
    if fmt in ("LP", "2xLP", "EP", "Single"):
        return "VINYL"
    if fmt in ("CD", "SACD"):
        return "CD"
    if fmt == "Cassette":
        return "CASSETTE"
    return None

# Аксессуары: магазины ставят их в общий каталог рядом с пластинками
# (пины-значки, пакеты, щётки, постеры, сертификаты), а парсер по дефолту
# помечает их `LP`. В Discogs их нет — каждый on-demand fetch заведомо вернёт
# None и впустую сожжёт квоту DISCOGS_FETCH_HOURLY_LIMIT, не давая дойти до
# реальных пластинок. Этот паттерн — короткий чёрный список по title.
_ACCESSORY_TITLE_RE = re.compile(
    r"\(Pin\)|\(пин\)|\bзначок\b|пакет\b|конверт\b|щётк|щетк|"
    r"кружк|брелок|постер|poster\b|плакат|сертификат|подарочн|"
    r"футболк|t[\-\s]?shirt|худи|hoodie|наклейк|sticker",
    re.IGNORECASE,
)


def _is_accessory(listing: StoreListing) -> bool:
    return bool(_ACCESSORY_TITLE_RE.search(listing.title_raw or ""))


# WS3.1 — нормализация artist/title перед similarity. Симметрично с обеих
# сторон (Python-параметр и SQL-колонка через _SQL_NORM), чтобы пунктуация и
# регистр не занижали score. Cyrillic сохраняется ([:alnum:] в UTF-8 ловит
# кириллицу). RU↔translit намеренно НЕ делаем — рискует смержить разные релизы;
# отложено. Thresholds (DEDUP/CROSS_SHOP) не трогаем — нормализация лишь
# убирает шум, поведение порога остаётся прежним.
_NORM_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_NORM_WS_RE = re.compile(r"\s+")
# SQL-зеркало нормализации: {col} → lower + не-alnum→пробел. Применяется к
# колонкам records.artist/title и store_listings.artist_raw/title_raw.
_SQL_NORM = "lower(regexp_replace({col}, '[^[:alnum:] ]+', ' ', 'g'))"


def _normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = _NORM_PUNCT_RE.sub(" ", s.lower())
    return _NORM_WS_RE.sub(" ", s).strip()

# Discogs on-demand: верхняя крышка против burst-нагрузки. Per-minute rate-limit
# (60 req/min) уже выровнен через discogs_limiter (TokenBucketRateLimiter capacity=55,
# refill_rate=0.95 = ~57 req/min). Hourly limit — это анти-DDOS для batch matcher'а:
# защищает от ситуации когда matcher разом хочет догнать 10к unmatched и за час
# вычерпает всю квоту, мешая live-запросам пользовательского поиска (Priority.SEARCH).
# При 2000/час среднее ~33 req/min — всё ещё в безопасной зоне 60/min.
# План разрешает (см. PARSING.md §5 «Что делать если хочется быстрее»).
DISCOGS_FETCH_HOURLY_LIMIT = 2000

# Store-native gate (см. шаг 6 в match_listing).
# Listing должен существовать достаточно долго ИЛИ быть подтверждённым из
# другого магазина, чтобы мы создали под него Record. Защита от опечаток парсера
# и краткоживущих листингов, которых на следующий день уже нет.
STORE_NATIVE_MIN_PERSIST_DAYS = 7
# Threshold для dedup среди уже созданных store-native: сумма similarity(artist) +
# similarity(title). pg_trgm возвращает [0, 1], так что 1.6 = в среднем 0.8 на поле.
# Подбирается эмпирически на проде, при ложных мерджах поднять.
STORE_NATIVE_DEDUP_SCORE = 1.6
# Cross-shop confirmation: ищем второй unmatched-листинг с похожим artist+title
# в другом store_id. Threshold по similarity — мягче, чем dedup (там consequences
# хуже — записи объединятся; здесь только подтверждение существования релиза).
STORE_NATIVE_CROSS_SHOP_SCORE = 1.4

# Авто-merge store-native → discogs: сколько раз подряд rematch должен
# подтвердить candidate, чтобы запустить safe-merge. 2 = две недели подряд
# weekly_rematch_store_native находит тот же discogs_id → объединяем.
# При смене candidate счётчик сбрасывается до 1.
STORE_NATIVE_MERGE_MIN_CONFIRMATIONS = 2


# ---- Discogs Releases Dump (slim local index) -------------------------- #


# Кэшируем результат проверки «есть ли вообще данные в дампе» — таблица
# может существовать но быть пустой (миграция применена, ingest не запущен).
# Сбрасывается при каждом перезапуске процесса; ингест на проде — редкое
# событие, in-process cache вместо Redis достаточен.
_dump_available: bool | None = None


async def _is_dump_available(db: AsyncSession) -> bool:
    """Лазает в таблицу один раз за процесс — после узнаём через cached flag."""
    global _dump_available
    if _dump_available is not None:
        return _dump_available
    try:
        res = await db.execute(text("SELECT 1 FROM discogs_releases_index LIMIT 1"))
        _dump_available = res.first() is not None
    except Exception:
        # Таблица не создана (миграция не применена)
        _dump_available = False
    return _dump_available


async def _lookup_in_dump_index(
    db: AsyncSession,
    *,
    barcode: str | None,
    catalog: str | None,
    artist: str | None,
    title: str | None,
    year: int | None,
    listing_format: str | None = None,
) -> tuple[dict, str, Decimal] | None:
    """Поиск в slim Discogs Dump. Возвращает (row, method, confidence) или None.

    Каскад: barcode (1.0) → catalog (0.9) → fuzzy artist+title (score-based).
    Без запроса к Discogs API — всё локально. Бьёт намного быстрее, чем
    on-demand /database/search.
    """
    if not await _is_dump_available(db):
        return None

    # 1) barcode — точный. Пробуем UPC↔EAN-13 варианты (§A WS-A4): дамп хранит
    # один товар то как UPC-A(12), то как EAN-13('0'+UPC), ~20% с лидирующим
    # нулём — без вариантов матч зависел бы от формы.
    if barcode:
        variants = barcode_variants(barcode)
        if variants:
            row = (await db.execute(
                text(
                    "SELECT discogs_id, master_id, artist, title, year, country, "
                    "       format_type, label, cover_image_url "
                    "FROM discogs_releases_index "
                    "WHERE barcode_norm = ANY(:bs) LIMIT 1"
                ),
                {"bs": variants},
            )).mappings().first()
            if row:
                return dict(row), MatchMethod.DUMP_INDEX, Decimal("1.000")

    # 2) catalog — точный
    if catalog:
        row = (await db.execute(
            text(
                "SELECT discogs_id, master_id, artist, title, year, country, "
                "       format_type, label, cover_image_url "
                "FROM discogs_releases_index "
                "WHERE catalog_norm = :c LIMIT 1"
            ),
            {"c": catalog},
        )).mappings().first()
        if row:
            return dict(row), MatchMethod.DUMP_INDEX, Decimal("0.900")

    # 3) fuzzy artist+title через pg_trgm. threshold 1.4 = в среднем 0.7 similarity
    # по каждому полю. Year-фильтр опционален — ±2 года или NULL.
    # Используем одиночный `%` (оператор pg_trgm similarity) — asyncpg не нуждается
    # в экранировании `%%` (это нужно только для psycopg2), и `%%` отправляется
    # в Postgres буквально как `%%`, вызывая UndefinedFunctionError.
    if artist and title:
        # LIMIT 5 (не 1): топ-кандидат может быть конфликтным по носителю
        # (CD-пресс выигрывает similarity у винила). Берём первого, чей
        # format_family совпадает с листингом (или неизвестен).
        rows = (await db.execute(
            text(
                "SELECT discogs_id, master_id, artist, title, year, country, "
                "       format_type, label, cover_image_url, "
                "       (similarity(artist, :a) + similarity(title, :t)) AS score "
                "FROM discogs_releases_index "
                "WHERE artist % :a AND title % :t "
                "  AND (cast(:y as int) IS NULL OR year IS NULL OR ABS(year - cast(:y as int)) <= 2) "
                "ORDER BY score DESC LIMIT 5"
            ),
            {"a": artist, "t": title, "y": year},
        )).mappings().all()
        lf = _format_family(listing_format)
        for row in rows:
            if not row.get("score") or row["score"] < 1.4:
                break  # отсортировано DESC — дальше только хуже
            rf = _format_family(row.get("format_type"))
            if lf and rf and lf != rf:
                continue  # конфликт носителя — пропускаем кандидата
            # Confidence масштабируем: 1.4 → 0.85, 2.0 → 0.95.
            conf = min(Decimal("0.950"), Decimal(str(round(0.5 + row["score"] * 0.25, 3))))
            return dict(row), MatchMethod.DUMP_INDEX, conf

    return None


async def _get_or_create_record_from_dump(
    db: AsyncSession, entry: dict,
) -> Record | None:
    """Берёт Record по discogs_id из БД или создаёт из dump-entry.

    tracklist + детальные данные подтянет _ensure_record_discogs_payload
    при первом детальном просмотре — здесь только минимум для матчинга.
    """
    discogs_id = str(entry["discogs_id"])
    existing = await _find_by_discogs_id(db, discogs_id)
    if existing:
        return existing

    rec = Record(
        discogs_id=discogs_id,
        discogs_master_id=str(entry["master_id"]) if entry.get("master_id") else None,
        title=entry["title"],
        artist=entry["artist"],
        label=entry.get("label"),
        year=entry.get("year"),
        country=entry.get("country"),
        format_type=entry.get("format_type"),
        cover_image_url=entry.get("cover_image_url"),
        discogs_data={},  # пусто — _ensure_record_discogs_payload догрузит
        source="discogs",
    )
    # Используем вложенный SAVEPOINT, не session.rollback() — иначе откатывается
    # вся внешняя транзакция (в т.ч. savepoint из rematch_store_native или
    # match_unmatched_batch), что приводит к ResourceClosedError при попытке
    # откатить уже закрытый sp. Паттерн идентичен _create_store_native_record.
    sp = await db.begin_nested()
    db.add(rec)
    try:
        await db.flush()
        await sp.commit()
        return rec
    except Exception:
        await sp.rollback()
        # Race: кто-то другой только что создал — читаем существующую
        existing = await _find_by_discogs_id(db, discogs_id)
        return existing


# ---- Поиск Record по идентификаторам ----------------------------------- #


async def _find_by_discogs_id(db: AsyncSession, discogs_id: str) -> Record | None:
    res = await db.execute(select(Record).where(Record.discogs_id == discogs_id))
    return res.scalar_one_or_none()


async def _find_by_barcode(db: AsyncSession, barcode: str) -> Record | None:
    # UPC↔EAN-13 варианты (§A WS-A4) — запись могла быть создана с другой формой.
    variants = barcode_variants(barcode)
    if not variants:
        return None
    res = await db.execute(select(Record).where(Record.barcode.in_(variants)))
    return res.scalars().first()


async def _find_by_catalog(db: AsyncSession, catalog_norm: str) -> Record | None:
    """Catalog в БД не нормализован — нормализуем на лету через regexp_replace."""
    res = await db.execute(
        text(
            "SELECT * FROM records "
            "WHERE upper(regexp_replace(catalog_number, '[ \\-_/.]', '', 'g')) = :cat "
            "LIMIT 1"
        ),
        {"cat": catalog_norm},
    )
    row = res.fetchone()
    if not row:
        return None
    rec = await db.execute(select(Record).where(Record.id == row.id))
    return rec.scalar_one_or_none()


async def _fuzzy_candidates(
    db: AsyncSession, artist: str | None, title: str | None
) -> list[Record]:
    """Кандидаты через pg_trgm. Если нет ни artist, ни title — пусто."""
    if not artist and not title:
        return []
    # Берём top-N кандидатов по similarity. Используем функцию `similarity()`
    # вместо оператора `%` — asyncpg не любит `%` в подготовленных запросах
    # (`UndefinedFunctionError` даже когда оператор есть в БД).
    # На малых records-таблицах seqscan мгновенный; на больших — pg_trgm GIN
    # индекс по `gin_trgm_ops` всё равно ускоряет similarity-сортировку.
    if title:
        sql = text(
            "SELECT * FROM records "
            "WHERE similarity(title::text, cast(:q as text)) >= :thr "
            "ORDER BY similarity(title::text, cast(:q as text)) DESC "
            "LIMIT :lim"
        )
        q = title
    else:
        sql = text(
            "SELECT * FROM records "
            "WHERE similarity(artist::text, cast(:q as text)) >= :thr "
            "ORDER BY similarity(artist::text, cast(:q as text)) DESC "
            "LIMIT :lim"
        )
        q = artist  # type: ignore[assignment]
    res = await db.execute(sql, {"q": q, "lim": FUZZY_CANDIDATES_LIMIT, "thr": 0.25})
    ids = [row.id for row in res.fetchall()]
    if not ids:
        return []
    res2 = await db.execute(select(Record).where(Record.id.in_(ids)))
    return list(res2.scalars().all())


def _record_color_family(rec: Record) -> str | None:
    """Семья цвета записи из discogs_data->vinyl_color_raw (=formats[0].text).

    color_family чистит шум (180 Gram / Jewel Case / Cinram → None), так что
    сюда попадает только реальный цвет.
    """
    data = rec.discogs_data or {}
    return color_family(data.get("vinyl_color_raw"))


def _fuzzy_score(rec: Record, listing: StoreListing) -> float:
    title_score = fuzz.token_sort_ratio(rec.title or "", listing.title_raw or "") / 100.0
    artist_score = (
        fuzz.token_sort_ratio(rec.artist or "", listing.artist_raw or "") / 100.0
        if listing.artist_raw else 0.5
    )
    year_bonus = 0.1 if (rec.year and listing.year_raw and rec.year == listing.year_raw) else 0.0
    score = min(1.0, title_score * 0.6 + artist_score * 0.3 + year_bonus)
    # Format-aware: если носитель листинга и записи известны и различны
    # (винил-листинг → CD-релиз), давим score ниже порога — иначе fuzzy
    # привязывает винил к CD-прессу, и хедер записи врёт «CD».
    lf, rf = _format_family(listing.format_raw), _format_family(rec.format_type)
    if lf and rf and lf != rf:
        score *= FORMAT_MISMATCH_PENALTY
    # Color-aware (§A WS-A1): обе семьи цвета известны и различны → давим ниже
    # порога. Без этого fuzzy привязывает чёрный листинг к зелёной записи и
    # выдаёт чужой пресс за «этот». Неизвестный цвет (одна из сторон) — не
    # штрафуем, чтобы не отсекать легитимные матчи без данных о цвете.
    lcf, rcf = color_family(listing.vinyl_color_raw), _record_color_family(rec)
    if lcf and rcf and lcf != rcf:
        score *= COLOR_MISMATCH_PENALTY
    return score


# ---- Главная функция матчинга ------------------------------------------ #


async def match_listing(listing: StoreListing, db: AsyncSession) -> bool:
    """Попытаться привязать листинг к Record. Возвращает True если матч найден.

    Не делает commit — вызывающий должен закоммитить.
    """
    raw = listing.raw_payload or {}

    # 1) Discogs URL
    discogs_url = raw.get("discogs_release_url")
    if discogs_url:
        # парсим release/<id>
        import re
        m = re.search(r"/release/(\d+)", discogs_url)
        if m:
            rec = await _find_by_discogs_id(db, m.group(1))
            if rec:
                _apply_match(listing, rec, Decimal("1.000"), MatchMethod.DISCOGS_URL)
                return True

    # 2) Barcode
    barcode_raw = raw.get("barcode") or listing.raw_payload.get("barcode") if listing.raw_payload else None
    barcode = normalize_barcode(barcode_raw)
    if barcode:
        rec = await _find_by_barcode(db, barcode)
        if rec:
            _apply_match(listing, rec, Decimal("1.000"), MatchMethod.BARCODE)
            return True

    # 3) Catalog
    catalog = normalize_catalog(raw.get("catalog_number"))
    if catalog:
        rec = await _find_by_catalog(db, catalog)
        if rec:
            _apply_match(listing, rec, Decimal("0.900"), MatchMethod.CATALOG)
            return True

    # 3.5) Exact dump lookup (barcode/catalog) ДО fuzzy — §A WS-A2.
    # barcode/catalog опознают КОНКРЕТНЫЙ пресс; локальный fuzzy (шаг 4)
    # опознаёт только альбом и может схлопнуть листинг на чужой пресс раньше,
    # чем мы найдём верный по barcode. Прогоняем exact-сигнал дампа вперёд.
    # artist/title=None → внутри _lookup_in_dump_index срабатывают только
    # barcode/catalog ветки (fuzzy-блок требует artist AND title). Создаёт
    # верный per-pressing Record если его ещё нет в БД.
    if barcode or catalog:
        exact_dump = await _lookup_in_dump_index(
            db,
            barcode=barcode,
            catalog=catalog,
            artist=None,
            title=None,
            year=listing.year_raw,
            listing_format=listing.format_raw,
        )
        if exact_dump:
            entry, method, conf = exact_dump
            rec = await _get_or_create_record_from_dump(db, entry)
            if rec:
                _apply_match(listing, rec, conf, method)
                return True

    # 4) Fuzzy
    candidates = await _fuzzy_candidates(db, listing.artist_raw, listing.title_raw)
    if candidates:
        best, best_score = None, 0.0
        for rec in candidates:
            score = _fuzzy_score(rec, listing)
            if score > best_score:
                best, best_score = rec, score
        if best and best_score >= FUZZY_THRESHOLD:
            _apply_match(listing, best, Decimal(str(round(best_score, 3))), MatchMethod.FUZZY)
            return True

    # 4.5) Slim Discogs Dump (local index) — barcode/catalog/fuzzy lookup
    # ДО on-demand Discogs API. Покрытие дампа 80%+ от всех релизов, поиск
    # быстрее чем сеть, не тратим квоту 60/min.
    dump_hit = await _lookup_in_dump_index(
        db,
        barcode=barcode,
        catalog=catalog,
        artist=listing.artist_raw,
        title=listing.title_raw,
        year=listing.year_raw,
        listing_format=listing.format_raw,
    )
    if dump_hit:
        entry, method, conf = dump_hit
        rec = await _get_or_create_record_from_dump(db, entry)
        if rec:
            _apply_match(listing, rec, conf, method)
            return True

    # 5) On-demand Discogs fetch — отдельная задача (не блокируем матчер)
    if barcode or catalog:
        rec = await _try_discogs_fetch(db, barcode=barcode, catalog=catalog)
        if rec:
            _apply_match(listing, rec, Decimal("0.950"), MatchMethod.DISCOGS_FETCH)
            return True

    # 5b) Fallback on-demand fetch by artist+title — для магазинов без barcode
    # (например, Plastinka.com публикует только название/артиста, без EAN).
    # Точность ниже чем barcode (Discogs search может вернуть похожий, но не
    # точно тот pressing), поэтому confidence 0.85 — на грани автоматического
    # acceptance. Если хочется строже — поднять FUZZY_THRESHOLD или вручную
    # модерировать через /admin/unmatched.
    if listing.artist_raw and listing.title_raw:
        rec = await _try_discogs_fetch_by_text(
            db,
            artist=listing.artist_raw,
            title=listing.title_raw,
            year=listing.year_raw,
        )
        if rec:
            _apply_match(listing, rec, Decimal("0.850"), MatchMethod.DISCOGS_FETCH)
            return True

    # 6) Store-native fallback: Discogs ничего не знает про этот релиз
    # (типичный кейс — русский инди вне Discogs). Создаём Record из данных
    # самого листинга. Под anti-noise gate (см. _should_create_store_native):
    # листинг должен прожить ≥7д ИЛИ быть подтверждён вторым магазином, и
    # иметь полный набор данных (artist+title+year+cover). Возвращаемый
    # объект может быть существующей store-native записью, если другой
    # магазин уже её создал (дедуп по fuzzy artist+title+year).
    if await _should_create_store_native(listing, db):
        rec = await _create_store_native_record(listing, db)
        if rec:
            _apply_match(listing, rec, Decimal("1.000"), MatchMethod.STORE_NATIVE)
            return True

    return False


def _apply_match(listing: StoreListing, rec: Record, conf: Decimal, method: str) -> None:
    listing.matched_record_id = rec.id
    listing.match_confidence = conf
    listing.match_method = method
    listing.matched_at = datetime.utcnow()


# ---- On-demand Discogs fetch ------------------------------------------- #


async def _try_discogs_fetch(
    db: AsyncSession, *, barcode: str | None, catalog: str | None
) -> Record | None:
    """Если у нас нет Record в БД, но есть barcode/catalog — попытаться найти на Discogs.

    Соблюдает hourly-лимит (Redis-counter), низкий приоритет.
    Создаёт Record в БД при успехе.
    """
    from app.services.cache import cache
    counter_key = "discogs_ondemand_hits"
    counter_ns = "scraper:counters"

    # Атомарный INCR через Redis (graceful fallback)
    if cache.available:
        try:
            assert cache._pool is not None
            redis_key = cache._key(counter_ns, counter_key)
            count = await cache._pool.incr(redis_key)
            if count == 1:
                await cache._pool.expire(redis_key, 3600)
            if count > DISCOGS_FETCH_HOURLY_LIMIT:
                return None
        except Exception:
            logger.debug("on-demand counter failed", exc_info=True)

    try:
        from app.services.discogs import DiscogsService
        from app.services.rate_limiter import Priority

        discogs = DiscogsService()
        params: dict = {"format": "Vinyl", "type": "release", "per_page": 5}
        if barcode:
            params["barcode"] = barcode
        elif catalog:
            params["catno"] = catalog

        results = await discogs._get(
            f"{discogs.BASE_URL}/database/search",
            params=params,
            priority=Priority.ENRICHMENT,
        )
        items = results.get("results", [])
        if not items:
            return None

        return await _save_discogs_result(db, items[0], barcode=barcode, catalog=catalog)
    except Exception:
        logger.exception("on-demand discogs fetch failed (barcode=%s catalog=%s)", barcode, catalog)
        return None


async def _try_discogs_fetch_by_text(
    db: AsyncSession, *, artist: str, title: str, year: int | None,
) -> Record | None:
    """
    Поиск Record через Discogs API по artist+title (для магазинов без barcode,
    например Plastinka.com). Соблюдает тот же hourly-counter что и barcode-fetch.
    Возвращает первый результат если matches достаточно близко по году.
    """
    from app.services.cache import cache
    counter_key = "discogs_ondemand_hits"
    counter_ns = "scraper:counters"

    if cache.available:
        try:
            assert cache._pool is not None
            redis_key = cache._key(counter_ns, counter_key)
            count = await cache._pool.incr(redis_key)
            if count == 1:
                await cache._pool.expire(redis_key, 3600)
            if count > DISCOGS_FETCH_HOURLY_LIMIT:
                return None
        except Exception:
            logger.debug("on-demand counter failed", exc_info=True)

    try:
        from app.services.discogs import DiscogsService
        from app.services.rate_limiter import Priority

        discogs = DiscogsService()
        params: dict = {
            "format": "Vinyl",
            "type": "release",
            "per_page": 5,
            "artist": artist,
            "release_title": title,
        }
        if year:
            params["year"] = year

        results = await discogs._get(
            f"{discogs.BASE_URL}/database/search",
            params=params,
            priority=Priority.ENRICHMENT,
        )
        items = results.get("results", [])
        if not items:
            return None

        # Берём первый — Discogs обычно выдаёт самый релевантный сверху.
        # Если есть год, дополнительно проверяем что найденный совпадает ±1 год
        # (Discogs иногда показывает re-issues с другим годом, нам важна суть).
        first = items[0]
        if year:
            found_year = first.get("year")
            try:
                if found_year and abs(int(found_year) - year) > 1:
                    return None
            except (ValueError, TypeError):
                pass

        return await _save_discogs_result(db, first, barcode=None, catalog=None)
    except Exception:
        logger.exception(
            "on-demand discogs fetch-by-text failed (artist=%s title=%s)", artist, title,
        )
        return None


async def _save_discogs_result(
    db: AsyncSession, first: dict, *, barcode: str | None, catalog: str | None,
) -> Record | None:
    """Общий хелпер: из Discogs search-результата создаёт Record (если ещё нет)."""
    discogs_id = str(first.get("id"))
    existing = await _find_by_discogs_id(db, discogs_id)
    if existing:
        return existing

    title = first.get("title", "")
    artist, _, album = title.partition(" - ")
    # Discogs search возвращает `format` как массив строк типа
    # ["Vinyl", "LP", "Album"] или ["CD", "Album", "Reissue"]. Берём первое
    # значимое имя (LP/CD/Cassette/Box Set) — этого хватает для отображения
    # в карусели. Без этого records.format_type был NULL у всех созданных
    # через on-demand fetch.
    fmt_arr = first.get("format") or []
    format_type = next(
        (f for f in fmt_arr if f and f.strip() not in ("Album", "Reissue", "Compilation")),
        fmt_arr[0] if fmt_arr else None,
    )
    rec = Record(
        discogs_id=discogs_id,
        title=album.strip() or title.strip(),
        artist=artist.strip() or "Unknown",
        year=int(first["year"]) if first.get("year") and str(first["year"]).isdigit() else None,
        barcode=barcode,
        catalog_number=(first.get("catno") or catalog),
        label=(first.get("label") or [None])[0],
        format_type=format_type,
        cover_image_url=first.get("cover_image"),
        thumb_image_url=first.get("thumb"),
        country=first.get("country"),
    )
    db.add(rec)
    await db.flush()
    return rec


# ---- Store-native fallback (шаг 6) ------------------------------------- #


async def _should_create_store_native(listing: StoreListing, db: AsyncSession) -> bool:
    """Anti-noise gate перед созданием store-native Record.

    ВСЕ условия должны быть true:
    1. Не аксессуар.
    2. Полный набор данных: artist + title + year + cover в raw_payload.
    3. Подтверждение существования (OR):
       a. last_seen_at - first_seen_at >= STORE_NATIVE_MIN_PERSIST_DAYS, ИЛИ
       b. есть второй unmatched листинг с похожим artist+title в другом store_id.
    """
    if _is_accessory(listing):
        return False
    if not listing.artist_raw or not listing.title_raw:
        return False
    if not (listing.raw_payload or {}).get("image_url"):
        return False

    # WS3.2 — доверенный магазин: создаём сразу, год опционален. Остальным
    # год обязателен (анти-шум) + persist/cross-shop подтверждение.
    from app.models.store import Store
    is_trusted = await db.scalar(
        select(Store.is_trusted).where(Store.id == listing.store_id)
    )
    if is_trusted:
        return True
    if not listing.year_raw:
        return False

    persisted_long = (
        listing.last_seen_at
        and listing.first_seen_at
        and (listing.last_seen_at - listing.first_seen_at) >= timedelta(days=STORE_NATIVE_MIN_PERSIST_DAYS)
    )
    if persisted_long:
        return True

    return await _has_cross_shop_confirmation(listing, db)


async def _has_cross_shop_confirmation(listing: StoreListing, db: AsyncSession) -> bool:
    """Существует ли второй unmatched-листинг похожего релиза в другом магазине."""
    na = _SQL_NORM.format(col="sl.artist_raw")
    nt = _SQL_NORM.format(col="sl.title_raw")
    sql = text(
        f"""
        SELECT 1
        FROM store_listings sl
        WHERE sl.matched_record_id IS NULL
          AND sl.id <> cast(:listing_id as uuid)
          AND sl.store_id <> cast(:store_id as uuid)
          AND sl.artist_raw IS NOT NULL
          AND sl.title_raw IS NOT NULL
          AND (similarity({na}, cast(:artist as text)) + similarity({nt}, cast(:title as text))) >= :thr
        LIMIT 1
        """
    )
    res = await db.execute(
        sql,
        {
            "listing_id": listing.id,
            "store_id": listing.store_id,
            "artist": _normalize_text(listing.artist_raw),
            "title": _normalize_text(listing.title_raw),
            "thr": STORE_NATIVE_CROSS_SHOP_SCORE,
        },
    )
    return res.first() is not None


async def _find_store_native_duplicate(
    db: AsyncSession, *, artist: str, title: str, year: int | None,
) -> Record | None:
    """Существующая store-native запись для того же релиза. Дедуп между магазинами."""
    # NB: явные касты ::text и ::int — asyncpg не определяет тип NULL-параметра,
    # без них падает AmbiguousParameterError на :year когда year=None.
    na = _SQL_NORM.format(col="artist")
    nt = _SQL_NORM.format(col="title")
    sql = text(
        f"""
        SELECT id, (similarity({na}, cast(:artist as text)) + similarity({nt}, cast(:title as text))) AS score
        FROM records
        WHERE source = 'store'
          AND (cast(:year as int) IS NULL OR year IS NULL OR ABS(year - cast(:year as int)) <= 1)
          AND (similarity({na}, cast(:artist as text)) + similarity({nt}, cast(:title as text))) >= :thr
        ORDER BY score DESC
        LIMIT 1
        """
    )
    row = (
        await db.execute(
            sql,
            {
                "artist": _normalize_text(artist),
                "title": _normalize_text(title),
                "year": year,
                "thr": STORE_NATIVE_DEDUP_SCORE,
            },
        )
    ).first()
    if not row:
        return None
    return await db.get(Record, row.id)


async def _create_store_native_record(
    listing: StoreListing, db: AsyncSession,
) -> Record | None:
    """Создать (или вернуть существующую) store-native запись под этот листинг.

    Перед INSERT проверяет дедуп. На случай конкурентного INSERT — ловит
    IntegrityError по partial unique index uq_store_native_artist_title_year
    и повторно ищет дубль.
    """
    from sqlalchemy.exc import IntegrityError

    raw = listing.raw_payload or {}

    existing = await _find_store_native_duplicate(
        db,
        artist=listing.artist_raw,
        title=listing.title_raw,
        year=listing.year_raw,
    )
    if existing:
        return existing

    rec = Record(
        source="store",
        discogs_id=None,
        artist=listing.artist_raw,
        title=listing.title_raw,
        year=listing.year_raw,
        format_type=listing.format_raw,
        cover_image_url=raw.get("image_url"),
        label=raw.get("label"),
        catalog_number=normalize_catalog(raw.get("catalog_number")),
        barcode=normalize_barcode(raw.get("barcode")),
    )
    # NESTED SAVEPOINT — match_listing уже внутри savepoint от batch-матчера;
    # ещё один уровень нужен, чтобы IntegrityError по partial unique index не
    # отравил всю outer-транзакцию. После .rollback() этого savepoint outer
    # остаётся живой, и мы можем продолжить запрос к records.
    sp = await db.begin_nested()
    db.add(rec)
    try:
        await db.flush()
        await sp.commit()
    except IntegrityError:
        # Параллельный INSERT успел вставить дубль — откатываем nested savepoint
        # и ищем существующий. Это редкий путь (batch-матчер однопоточен), но
        # покрывает CLI-вызовы и будущую параллелизацию scraper'ов.
        await sp.rollback()
        return await _find_store_native_duplicate(
            db,
            artist=listing.artist_raw,
            title=listing.title_raw,
            year=listing.year_raw,
        )

    # Hot-link обложки магазина может протухнуть — копируем к себе в S3/локальный
    # кэш. fire-and-forget, отдельная сессия БД.
    image_url = raw.get("image_url")
    if image_url:
        from app.services.cover_storage import schedule_store_native_cover_cache
        schedule_store_native_cover_cache(rec.id, image_url)

    logger.info(
        "store-native: created Record %s for listing %s (artist=%s title=%s year=%s)",
        rec.id, listing.id, listing.artist_raw, listing.title_raw, listing.year_raw,
    )
    return rec


# ---- Batch-матчер для cron --------------------------------------------- #


async def match_unmatched_batch(batch_size: int = 200) -> dict[str, int]:
    """Найти `batch_size` unmatched листингов и попытаться сматчить.

    Возвращает счётчики: matched/unmatched/errors + диагностика по сигналам
    (какие из источников ID у листингов вообще есть).
    """
    counters = {
        "processed": 0,
        "matched": 0,
        "unmatched": 0,
        "errors": 0,
        "skipped_accessory": 0,
        "store_native_created": 0,
    }
    # Диагностика: сколько unmatched листингов вообще имеют сигналы для матчинга.
    # Без неё непонятно, парсер ли не вытаскивает barcode/discogs_url, или
    # matcher не находит. Лог помогает увидеть это сразу в выводе батча.
    signals = {"with_discogs_url": 0, "with_barcode": 0, "with_catalog": 0, "no_ids": 0}
    async with async_session_maker() as db:
        res = await db.execute(
            select(StoreListing)
            .where(StoreListing.matched_record_id.is_(None))
            .where(StoreListing.status.in_(("in_stock", "preorder")))
            .order_by(StoreListing.first_seen_at.asc())
            .limit(batch_size)
        )
        listings = list(res.scalars().all())

        for listing in listings:
            counters["processed"] += 1
            if _is_accessory(listing):
                counters["skipped_accessory"] += 1
                counters["unmatched"] += 1
                continue
            raw = listing.raw_payload or {}
            has_url = bool(raw.get("discogs_release_url"))
            has_bc = bool(raw.get("barcode"))
            has_cat = bool(raw.get("catalog_number"))
            if has_url:
                signals["with_discogs_url"] += 1
            if has_bc:
                signals["with_barcode"] += 1
            if has_cat:
                signals["with_catalog"] += 1
            if not (has_url or has_bc or has_cat):
                signals["no_ids"] += 1

            # SAVEPOINT — если match_listing уронит транзакцию, откатываем
            # только этот savepoint, остальные листинги продолжаем матчить.
            sp = await db.begin_nested()
            try:
                ok = await match_listing(listing, db)
                await sp.commit()
                counters["matched" if ok else "unmatched"] += 1
                if ok and listing.match_method == MatchMethod.STORE_NATIVE:
                    counters["store_native_created"] += 1
            except Exception:
                await sp.rollback()
                counters["errors"] += 1
                logger.exception("match failed for listing %s", listing.id)
                continue

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            counters["errors"] += counters["matched"]
            counters["matched"] = 0
            logger.exception("commit failed in match_unmatched_batch")

    logger.info("match batch: %s | signals: %s", counters, signals)
    return counters


# ---- Weekly re-match для store-native записей -------------------------- #


async def rematch_format_conflicts_batch(batch_size: int = 500) -> dict[str, int]:
    """Сброс matched-листингов, у которых носитель конфликтует с записью.

    Кейс: винил-листинг исторически привязан к CD-релизу (fuzzy до того, как
    появился format-penalty). Хедер записи тогда врёт «CD». match_unmatched_batch
    такие НЕ трогает (фильтрует matched_record_id IS NULL), поэтому чиним точечно:
    находим конфликт семьи формата → сбрасываем привязку в NULL. Следующий
    hourly_match_unmatched пере-привяжет уже с penalty → правильный носитель
    (или оставит unmatched, что лучше, чем врущий «CD»).

    STORE_NATIVE пропускаем — у них format_type записи выведен из самого
    листинга, конфликта по определению нет, а сброс сломал бы merge-цепочку.

    Возвращает: scanned, conflicts_reset, errors.
    """
    counters = {"scanned": 0, "conflicts_reset": 0, "errors": 0}
    affected_discogs_ids: set[str] = set()
    async with async_session_maker() as db:
        res = await db.execute(
            select(StoreListing, Record)
            .join(Record, Record.id == StoreListing.matched_record_id)
            .where(StoreListing.matched_record_id.is_not(None))
            .where(StoreListing.status.in_(("in_stock", "preorder")))
            .where(StoreListing.match_method != MatchMethod.STORE_NATIVE)
            .where(StoreListing.format_raw.is_not(None))
            .where(Record.format_type.is_not(None))
            .order_by(StoreListing.matched_at.asc())
            .limit(batch_size)
        )
        rows = res.all()
        for listing, rec in rows:
            counters["scanned"] += 1
            lf = _format_family(listing.format_raw)
            rf = _format_family(rec.format_type)
            if not (lf and rf and lf != rf):
                continue
            listing.matched_record_id = None
            listing.match_confidence = None
            listing.match_method = None
            listing.matched_at = None
            counters["conflicts_reset"] += 1
            if rec.discogs_id:
                affected_discogs_ids.add(rec.discogs_id)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            counters["errors"] += counters["conflicts_reset"]
            counters["conflicts_reset"] = 0
            logger.exception("commit failed in rematch_format_conflicts_batch")
            return counters

    # Сброс offers-кэша затронутых записей — иначе до TTL юзер видит старый
    # (конфликтный) оффер. Function-level import во избежание циклической
    # зависимости с app.api.offers.
    if affected_discogs_ids:
        try:
            from app.api.offers import invalidate_record_offers
            for did in affected_discogs_ids:
                await invalidate_record_offers(did)
        except Exception:
            logger.exception("offers cache invalidation failed after format rematch")

    logger.info("format-conflict rematch: %s", counters)
    return counters


async def rematch_album_with_barcode_batch(batch_size: int = 300) -> dict[str, int]:
    """Перематчить album-tier листинги, у которых появился barcode (§A WS-A4.5).

    Кейс: чёрный In Utero исторически привязан fuzzy к зелёной записи. После
    A4 (фикс normalize_barcode для SKU-паддинга) у листинга в raw_payload теперь
    есть barcode, опознающий КОНКРЕТНЫЙ пресс. Но match_unmatched_batch такие не
    трогает (matched_record_id IS NOT NULL), поэтому чиним точечно.

    Берём листинги, сматченные слабым методом (fuzzy / dump_index / discogs_fetch
    с confidence < 0.95 = album-tier), у которых в raw_payload есть barcode.
    Делаем rematch ИНЛАЙН со сравнением: пробуем match_listing заново; оставляем
    новый матч только если он успешен (иначе восстанавливаем старую связь —
    оффер не должен пропасть). Если новый record отличается — инвалидируем кэш
    обеих записей. Inline-сравнение исключает loop/churn: barcode-матч даёт
    dump_index conf 1.0 → в следующий заход уже не попадает.

    Возвращает: scanned, remapped, unchanged, errors.
    """
    counters = {"scanned": 0, "remapped": 0, "unchanged": 0, "errors": 0}
    affected_discogs_ids: set[str] = set()
    async with async_session_maker() as db:
        res = await db.execute(
            select(StoreListing)
            .where(StoreListing.matched_record_id.is_not(None))
            .where(StoreListing.status.in_(("in_stock", "preorder")))
            .where(StoreListing.match_method.in_(
                (MatchMethod.FUZZY, MatchMethod.DUMP_INDEX, MatchMethod.DISCOGS_FETCH)
            ))
            .where(or_(
                StoreListing.match_confidence.is_(None),
                StoreListing.match_confidence < Decimal("0.95"),
            ))
            .where(func.jsonb_exists(StoreListing.raw_payload, "barcode"))
            .order_by(StoreListing.matched_at.asc())
            .limit(batch_size)
        )
        listings = list(res.scalars().all())

        for listing in listings:
            counters["scanned"] += 1
            old_id = listing.matched_record_id
            old_method = listing.match_method
            old_conf = listing.match_confidence
            old_at = listing.matched_at
            old_rec = await db.get(Record, old_id) if old_id else None
            old_did = old_rec.discogs_id if old_rec else None

            sp = await db.begin_nested()
            try:
                listing.matched_record_id = None
                listing.match_confidence = None
                listing.match_method = None
                listing.matched_at = None
                ok = await match_listing(listing, db)
                await sp.commit()
            except Exception:
                await sp.rollback()
                # Восстанавливаем старую связь — не оставляем оффер висеть.
                listing.matched_record_id = old_id
                listing.match_method = old_method
                listing.match_confidence = old_conf
                listing.matched_at = old_at
                counters["errors"] += 1
                logger.exception("rematch-barcode failed for listing %s", listing.id)
                continue

            new_id = listing.matched_record_id
            if ok and new_id is not None:
                if new_id != old_id:
                    counters["remapped"] += 1
                    if old_did:
                        affected_discogs_ids.add(old_did)
                    new_rec = await db.get(Record, new_id)
                    if new_rec and new_rec.discogs_id:
                        affected_discogs_ids.add(new_rec.discogs_id)
                else:
                    counters["unchanged"] += 1
            else:
                # Rematch не нашёл — восстанавливаем прежнюю связь (оффер не теряем).
                listing.matched_record_id = old_id
                listing.match_method = old_method
                listing.match_confidence = old_conf
                listing.matched_at = old_at
                counters["unchanged"] += 1

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            counters["errors"] += counters["remapped"]
            counters["remapped"] = 0
            logger.exception("commit failed in rematch_album_with_barcode_batch")
            return counters

    if affected_discogs_ids:
        try:
            from app.api.offers import invalidate_record_offers
            for did in affected_discogs_ids:
                await invalidate_record_offers(did)
        except Exception:
            logger.exception("offers cache invalidation failed after barcode rematch")

    logger.info("album-barcode rematch: %s", counters)
    return counters


async def rematch_store_native_batch(batch_size: int = 200) -> dict[str, int]:
    """Прогнать store-native записи через Discogs search — может, релиз уже там.

    На совпадение пишем records.discogs_id_candidate и инкрементируем счётчик
    подтверждений. Когда тот же candidate подтверждается ≥ STORE_NATIVE_MERGE_MIN_CONFIRMATIONS
    раз подряд (обычно через 2 запуска weekly cron'а — две недели), запускаем
    safe_merge_store_native_into → переносим листинги, soft-delete'аем store-native.

    Берём записи source='store' с merged_into_id IS NULL: и новых кандидатов,
    и повторное подтверждение существующих. Сортируем по updated_at ASC —
    давно нетронутые попадают первыми.

    Возвращает счётчики: processed, candidates_found, candidates_confirmed,
    candidates_changed, merged, no_match, errors.
    """
    counters = {
        "processed": 0,
        "candidates_found": 0,       # новый candidate появился впервые
        "candidates_confirmed": 0,   # тот же candidate — счётчик++
        "candidates_changed": 0,     # другой candidate — сбрасываем
        "merged": 0,                 # auto-merge сработал
        "no_match": 0,
        "errors": 0,
    }
    async with async_session_maker() as db:
        res = await db.execute(
            select(Record)
            .where(Record.source == "store")
            .where(Record.merged_into_id.is_(None))
            .order_by(Record.updated_at.asc())
            .limit(batch_size)
        )
        records = list(res.scalars().all())

        for rec in records:
            counters["processed"] += 1
            sp = await db.begin_nested()
            try:
                # WS3.3 — каскад сигналов от точного к нечёткому: barcode/catalog
                # (exact, низкий риск ложного кандидата) → текст. NB:
                # _try_discogs_fetch* создаёт Record при успехе — это ОК (новая
                # Discogs-запись пригодится для других листингов), её discogs_id
                # прикрепляем к store-native через candidate. Auto-merge всё равно
                # ждёт ≥STORE_NATIVE_MERGE_MIN_CONFIRMATIONS подтверждений.
                found = None
                if rec.barcode:
                    found = await _try_discogs_fetch(db, barcode=rec.barcode, catalog=None)
                if not found and rec.catalog_number:
                    found = await _try_discogs_fetch(db, barcode=None, catalog=rec.catalog_number)
                if not found:
                    found = await _try_discogs_fetch_by_text(
                        db,
                        artist=rec.artist,
                        title=rec.title,
                        year=rec.year,
                    )
                if not (found and found.discogs_id and found.id != rec.id):
                    counters["no_match"] += 1
                    await sp.commit()
                    continue

                now = datetime.utcnow()
                if rec.discogs_id_candidate == found.discogs_id:
                    rec.discogs_id_candidate_confirmations += 1
                    counters["candidates_confirmed"] += 1
                elif rec.discogs_id_candidate is None:
                    rec.discogs_id_candidate = found.discogs_id
                    rec.discogs_id_candidate_first_seen_at = now
                    rec.discogs_id_candidate_confirmations = 1
                    counters["candidates_found"] += 1
                else:
                    # candidate сменился — это может быть и шум, и более точный
                    # match (Discogs обновил indexing). Сбрасываем счётчик: ждём
                    # повторного подтверждения нового кандидата.
                    rec.discogs_id_candidate = found.discogs_id
                    rec.discogs_id_candidate_first_seen_at = now
                    rec.discogs_id_candidate_confirmations = 1
                    counters["candidates_changed"] += 1
                    logger.info(
                        "rematch store-native: %s candidate changed → %s "
                        "(artist=%s title=%s)",
                        rec.id, found.discogs_id, rec.artist, rec.title,
                    )

                if rec.discogs_id_candidate_confirmations >= STORE_NATIVE_MERGE_MIN_CONFIRMATIONS:
                    merge_res = await safe_merge_store_native_into(
                        rec, rec.discogs_id_candidate, db, merged_by="cron",
                    )
                    if merge_res["target_found"]:
                        counters["merged"] += 1
                        logger.info(
                            "rematch store-native: AUTO-MERGED %s → discogs_id=%s "
                            "(remapped %d listings, artist=%s title=%s)",
                            rec.id, rec.discogs_id_candidate,
                            merge_res["listings_remapped"], rec.artist, rec.title,
                        )

                await sp.commit()
            except Exception:
                await sp.rollback()
                counters["errors"] += 1
                logger.exception("rematch failed for record %s", rec.id)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            counters["errors"] += counters["candidates_found"] + counters["merged"]
            counters["candidates_found"] = 0
            counters["merged"] = 0
            logger.exception("commit failed in rematch_store_native_batch")

    logger.info("rematch store-native batch: %s", counters)
    return counters


# ---- Safe merge store-native → discogs ---------------------------------- #


async def safe_merge_store_native_into(
    source: Record,
    target_discogs_id: str,
    db: AsyncSession,
    *,
    merged_by: str,
) -> dict[str, int]:
    """Объединить store-native Record в существующий Discogs Record.

    Шаги (внутри savepoint в вызывающем коде — мы не открываем свой):
      1. Найти/создать target Record по discogs_id (без on-demand Discogs API —
         только локальный SELECT, чтобы не зависеть от 60 req/min при batch'е).
      2. Перепривязать все store_listings.matched_record_id с source.id на target.id,
         выставить match_method = MERGED_FROM_STORE_NATIVE.
      3. Записать в record_merge_history snapshot полей source.
      4. Soft-delete source: записать merged_into_id = target.id.
         Физически НЕ удаляем — старые deep-link на uuid должны редиректить.

    Возвращает счётчики: listings_remapped + флаг target_found.
    Если target Record в локальной БД не нашёлся — возвращает {target_found: 0}
    и НИЧЕГО не меняет (caller волен сделать get_or_create через Discogs API).
    """
    counters = {"listings_remapped": 0, "target_found": 0}

    target_res = await db.execute(
        select(Record).where(Record.discogs_id == target_discogs_id)
    )
    target = target_res.scalar_one_or_none()
    if target is None:
        return counters
    if target.id == source.id:
        return counters

    counters["target_found"] = 1

    remap_res = await db.execute(
        text(
            "UPDATE store_listings "
            "SET matched_record_id = :tgt, "
            "    match_method = :method, "
            "    matched_at = :ts "
            "WHERE matched_record_id = :src"
        ),
        {
            "tgt": target.id,
            "src": source.id,
            "method": MatchMethod.MERGED_FROM_STORE_NATIVE,
            "ts": datetime.utcnow(),
        },
    )
    counters["listings_remapped"] = remap_res.rowcount or 0

    await db.execute(
        text(
            "INSERT INTO record_merge_history "
            "(source_record_id, target_record_id, source_artist, source_title, "
            " source_year, source_discogs_id_candidate, listings_remapped, merged_by) "
            "VALUES (:src, :tgt, :artist, :title, :year, :cand, :remapped, :merged_by)"
        ),
        {
            "src": source.id,
            "tgt": target.id,
            "artist": source.artist,
            "title": source.title,
            "year": source.year,
            "cand": source.discogs_id_candidate,
            "remapped": counters["listings_remapped"],
            "merged_by": merged_by,
        },
    )

    # Ремап коллекций/вишлистов: юзер мог добавить store-native в коллекцию ДО
    # merge. collection_items.record_id указывает на source — переносим на target,
    # иначе после soft-delete source запись «зависает» (get_record следует
    # merged_into_id, но isOwned(discogs_id) дрифтует, возможен дубль). Сначала
    # DELETE пересечений (target уже в той же коллекции/вишлисте — unique
    # (collection_id, record_id)), затем UPDATE остатка.
    for table, parent_col in (
        ("collection_items", "collection_id"),
        ("wishlist_items", "wishlist_id"),
    ):
        await db.execute(
            text(
                f"DELETE FROM {table} src "
                f"WHERE src.record_id = :src "
                f"  AND EXISTS (SELECT 1 FROM {table} dst "
                f"              WHERE dst.record_id = :tgt "
                f"                AND dst.{parent_col} = src.{parent_col})"
            ),
            {"src": source.id, "tgt": target.id},
        )
        await db.execute(
            text(f"UPDATE {table} SET record_id = :tgt WHERE record_id = :src"),
            {"tgt": target.id, "src": source.id},
        )

    source.merged_into_id = target.id
    # User-record слита в Discogs-аналог → статус 'merged' (§6/§7). Покрывает
    # оба пути rematch (dump + live API), т.к. merge всегда идёт через сюда.
    if source.source == "user":
        source.moderation_status = "merged"
    return counters
