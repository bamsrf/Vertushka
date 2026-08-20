"""Улики ачивок: «за какую музыку это получено».

В момент анлока ядро (evaluator.py) находит билдер по коду ачивки и кладёт
результат в `UserAchievement.ach_metadata["evidence"]` — замороженный снапшот,
как xp_awarded: продал пластинку — улика в истории осталась.

Принципы (зафиксированы владельцем):
- подсвечиваем ТОЛЬКО музыку — никаких имён людей (у подарков показываем
  пластинку, не получателя/дарителя);
- текст максимально короткий: «Artist — Title · и ещё 24».

Формат evidence: {"records": [{id, artist, title, year}], "count": N, "note": s}
— всё опционально. Текст собирается в `evidence_text()` — единственное место
копирайта, его же используют API и share-карточка. Структура в metadata
позволяет менять формулировки без бэкфилла.

Билдеры живут в EVIDENCE_BUILDERS (код → корутина), а не полем в
AchievementDefinition: одно место, где видно всё покрытие, и ноль правок в
файлах серий.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.record import Record
from app.models.wishlist import Wishlist, WishlistItem

EvidenceBuilder = Callable[
    [AsyncSession, "UUID", dict[str, Any]], Awaitable[dict[str, Any] | None]
]

#: Сколько записей храним в улике. Показываем одну, остальное — «и ещё N».
_SAMPLE_LIMIT = 3
#: Потолок длины «Artist — Title» в готовом тексте.
_LINE_MAX = 48


# --- Текст -------------------------------------------------------------------

def _shorten(s: str, limit: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _record_line(ref: dict[str, Any]) -> str | None:
    artist = (ref.get("artist") or "").strip()
    title = (ref.get("title") or "").strip()
    if not artist and not title:
        return None
    line = f"{artist} — {title}" if artist and title else (artist or title)
    return _shorten(line, _LINE_MAX)


def evidence_text(metadata: dict[str, Any] | None) -> str | None:
    """Короткий текст улики из ach_metadata. None — показывать нечего.

    Понимает и «легаси»-ключи H-серии (artist_name/master_name/label_name),
    которые дискография писала до появления evidence.
    """
    if not isinstance(metadata, dict):
        return None

    ev = metadata.get("evidence")
    if isinstance(ev, dict):
        parts: list[str] = []
        records = ev.get("records") or []
        if records and isinstance(records[0], dict):
            line = _record_line(records[0])
            if line:
                parts.append(line)
        count = ev.get("count")
        if isinstance(count, int) and count > 1 and records:
            parts.append(f"и ещё {count - 1}")
        note = (ev.get("note") or "").strip()
        if note:
            parts.append(note)
        return " · ".join(parts) if parts else None

    # Легаси H-серии: имя уже лежит в metadata, просто показываем.
    for key in ("artist_name", "master_name", "label_name"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return _shorten(value, _LINE_MAX)
    return None


# --- Общие выборки -------------------------------------------------------------

def _ref(record: Record) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "artist": record.artist,
        "title": record.title,
        "year": record.year,
    }


def _default_collection_id(user_id: UUID):
    return (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )


def _sql_sampler(*filters) -> EvidenceBuilder:
    """Улика из основной коллекции по SQL-фильтру: свежие первыми + счёт."""

    async def builder(db: AsyncSession, user_id: UUID, payload: dict) -> dict | None:
        base = (
            select(Record)
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .where(
                CollectionItem.collection_id == _default_collection_id(user_id),
                *filters,
            )
        )
        rows = await db.execute(
            base.order_by(CollectionItem.added_at.desc()).limit(_SAMPLE_LIMIT)
        )
        records = list({r.id: r for r in rows.scalars().all()}.values())
        if not records:
            return None
        count = await db.scalar(
            select(func.count(func.distinct(CollectionItem.record_id)))
            .join(Record, Record.id == CollectionItem.record_id)
            .where(
                CollectionItem.collection_id == _default_collection_id(user_id),
                *filters,
            )
        )
        return {"records": [_ref(r) for r in records], "count": int(count or 0)}

    return builder


def _python_sampler(predicate) -> EvidenceBuilder:
    """Улика по предикату над Record (для media_format/пасхалок): SQL-ем
    дескрипторы формата и JSON-поля не разберёшь."""

    async def builder(db: AsyncSession, user_id: UUID, payload: dict) -> dict | None:
        rows = await db.execute(
            select(Record)
            .join(CollectionItem, CollectionItem.record_id == Record.id)
            .where(CollectionItem.collection_id == _default_collection_id(user_id))
            .order_by(CollectionItem.added_at.desc())
            .limit(3000)
        )
        matched: list[Record] = []
        seen: set = set()
        for record in rows.scalars().all():
            if record.id in seen:
                continue
            seen.add(record.id)
            try:
                if predicate(record):
                    matched.append(record)
            except Exception:  # noqa: BLE001 — грязные данные не валят улику
                continue
        if not matched:
            return None
        return {
            "records": [_ref(r) for r in matched[:_SAMPLE_LIMIT]],
            "count": len(matched),
        }

    return builder


def _gift_record_builder(*, received: bool) -> EvidenceBuilder:
    """Пластинка подарка. Только музыка — получателя/дарителя не подсвечиваем.

    Сначала бронь из payload (живое событие), иначе — последний завершённый
    подарок юзера (бэкфилл/догон). count — сколько всего долетело.
    """

    async def builder(db: AsyncSession, user_id: UUID, payload: dict) -> dict | None:
        side = (
            GiftBooking.recipient_user_id if received else GiftBooking.booked_by_user_id
        )
        booking = None
        booking_id = (payload or {}).get("booking_id")
        if booking_id:
            booking = await db.scalar(
                select(GiftBooking).where(GiftBooking.id == booking_id)
            )
        if booking is None:
            booking = await db.scalar(
                select(GiftBooking)
                .where(side == user_id, GiftBooking.status == GiftStatus.COMPLETED)
                .order_by(GiftBooking.completed_at.desc().nulls_last())
                .limit(1)
            )
        if booking is None or booking.record_id is None:
            return None
        record = await db.scalar(select(Record).where(Record.id == booking.record_id))
        if record is None:
            return None
        count = await db.scalar(
            select(func.count()).select_from(GiftBooking).where(
                side == user_id, GiftBooking.status == GiftStatus.COMPLETED
            )
        )
        return {"records": [_ref(record)], "count": int(count or 0)}

    return builder


async def _crown_jewel_builder(
    db: AsyncSession, user_id: UUID, payload: dict
) -> dict | None:
    """Самая дорогая пластинка — та самая «Жемчужина». Цену в улику не пишем
    (на share-карточке ей не место), только музыку."""
    from app.config import get_settings
    from app.services.exchange import get_usd_rub_rate
    from app.services.pricing import PricingParams
    from app.services.valuation import record_value_rub

    rows = await db.execute(
        select(Record)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.user_id == user_id)
    )
    records = list({r.id: r for r in rows.scalars().all()}.values())
    if not records:
        return None
    rate = await get_usd_rub_rate()
    params = PricingParams.from_settings(get_settings())
    best = max(records, key=lambda r: record_value_rub(r, rate, params))
    return {"records": [_ref(best)]}


async def _time_machine_builder(
    db: AsyncSession, user_id: UUID, payload: dict
) -> dict | None:
    """Пластинка, добравшаяся ровно через 50 лет: нужен added_at, поэтому
    предикатом по Record не обойтись."""
    rows = await db.execute(
        select(Record, CollectionItem.added_at)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(CollectionItem.collection_id == _default_collection_id(user_id))
        .limit(3000)
    )
    for record, added_at in rows.all():
        if record.year and added_at is not None and added_at.year - record.year == 50:
            return {"records": [_ref(record)], "note": f"{record.year} → {added_at.year}"}
    return None


def _hot_wishlist_builder() -> EvidenceBuilder:
    async def builder(db: AsyncSession, user_id: UUID, payload: dict) -> dict | None:
        rows = await db.execute(
            select(Record)
            .join(WishlistItem, WishlistItem.record_id == Record.id)
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .where(Wishlist.user_id == user_id, Record.is_hot.is_(True))
            .order_by(WishlistItem.added_at.desc())
            .limit(_SAMPLE_LIMIT)
        )
        records = list({r.id: r for r in rows.scalars().all()}.values())
        if not records:
            return None
        count = await db.scalar(
            select(func.count(func.distinct(WishlistItem.record_id)))
            .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
            .join(Record, Record.id == WishlistItem.record_id)
            .where(Wishlist.user_id == user_id, Record.is_hot.is_(True))
        )
        return {"records": [_ref(r) for r in records], "count": int(count or 0)}

    return builder


# --- Предикаты для media/пасхалок ----------------------------------------------

def _media(record: Record):
    from app.services.achievements.media_format import parse_media

    return parse_media(record.format_type, record.format_description)


def _is_palindrome_year(record: Record) -> bool:
    year = record.year
    if not year or year < 1000:
        return False
    return str(year) == str(year)[::-1]


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


# --- Реестр билдеров -------------------------------------------------------------

def _build_registry() -> dict[str, EvidenceBuilder]:
    from app.services.achievements.definitions.eggs import (
        _HIDDEN_TITLE_TOKENS,
        GIANT_BOX_DISCS,
    )
    from app.services.achievements.definitions.random import (
        _META_VERTUSHKA_TOKENS,
        _SELF_AWARE_TOKENS,
        LONG_TITLE_THRESHOLD,
        _contains_any,
    )
    from app.services.achievements.media_format import BOX_SET, CASSETTE, CD, VINYL

    limited = _sql_sampler(Record.is_limited.is_(True))
    collectible = _sql_sampler(Record.is_collectible.is_(True))
    hot = _sql_sampler(Record.is_hot.is_(True))
    gift_done = _gift_record_builder(received=False)
    gift_received = _gift_record_builder(received=True)

    def _has_hidden_track(record: Record) -> bool:
        for track in record.tracklist or []:
            if not isinstance(track, dict):
                continue
            title = (track.get("title") or "").strip()
            if not title:
                continue
            position = (track.get("position") or "").strip()
            duration = (track.get("duration") or "").strip()
            if not position and duration:
                return True
            if any(tok in title.lower() for tok in _HIDDEN_TITLE_TOKENS):
                return True
        return False

    return {
        # Редкости
        "C1_limited_x5": limited,
        "C2_limited_x25": limited,
        "C3_collectible_x1": collectible,
        "C4_collectible_x5": collectible,
        "C5_collectible_x15": collectible,
        "C6_hot_in_wishlist": _hot_wishlist_builder(),
        "C7_hot_in_collection": hot,
        # География
        "D4_japanese_x10": _sql_sampler(Record.country.ilike("%japan%")),
        "D5_melodiya_x10": _sql_sampler(
            Record.label.ilike("%melodiya%") | Record.label.ilike("%мелодия%")
        ),
        "D6_uk_collectible_x3": _sql_sampler(
            Record.is_collectible.is_(True),
            func.lower(Record.country).in_(("uk", "united kingdom")),
        ),
        "D7_german_x10": _sql_sampler(Record.country.ilike("%germany%")),
        # Жанры
        "F3_jazz_x25": _sql_sampler(Record.genre.ilike("%jazz%")),
        "F4_electronic_x25": _sql_sampler(Record.genre.ilike("%electronic%")),
        "F5_classical_x15": _sql_sampler(Record.genre.ilike("%classical%")),
        "F6_rock_x25": _sql_sampler(Record.genre.ilike("%rock%")),
        # Стоимость
        "MV_crown_jewel": _crown_jewel_builder,
        # Форматы: первые-в-роде (счётчиковым хватает прогресса)
        "FMT1_beyond_vinyl": _python_sampler(
            lambda r: any(f != VINYL for f in _media(r).families)
        ),
        "T1_first_tape": _python_sampler(lambda r: _media(r).has(CASSETTE)),
        "CD1_first_cd": _python_sampler(lambda r: _media(r).has(CD)),
        "BX1_first_box": _python_sampler(lambda r: _media(r).has(BOX_SET)),
        # Подарки — только музыка
        "J1_first_gift": gift_done,
        "J2_gift_done": gift_done,
        "J3_three_recipients": gift_done,
        "J4_ten_recipients": gift_done,
        "J5_first_received": gift_received,
        "J7_boomerang": gift_done,
        "J8_loved": gift_received,
        "J9_santa": gift_done,
        # Пасхалки про конкретную пластинку
        "R_palindrome": _python_sampler(_is_palindrome_year),
        "R_self_titled": _python_sampler(
            lambda r: bool(_norm(r.title)) and _norm(r.title) == _norm(r.artist)
        ),
        "R_self_aware": _python_sampler(
            lambda r: _contains_any(r.title or "", _SELF_AWARE_TOKENS)
        ),
        "R_meta_vertushka": _python_sampler(
            lambda r: _contains_any(r.title or "", _META_VERTUSHKA_TOKENS)
            or _contains_any(r.artist or "", _META_VERTUSHKA_TOKENS)
        ),
        "R_long_title": _python_sampler(
            lambda r: len(r.title or "") > LONG_TITLE_THRESHOLD
        ),
        "R_time_machine_50": _time_machine_builder,
        "R_tabletop_giant": _python_sampler(
            lambda r: _media(r).has(BOX_SET) and _media(r).qty >= GIANT_BOX_DISCS
        ),
        "R_type_iv": _python_sampler(lambda r: _media(r).is_type_iv),
        "R_limited_box": _python_sampler(
            lambda r: _media(r).has(BOX_SET) and _media(r).is_limited
        ),
        "R_hidden_track": _python_sampler(_has_hidden_track),
        "E_glow": _python_sampler(
            lambda r: "glow" in ((r.discogs_data or {}).get("vinyl_color_raw") or "").lower()
        ),
    }


_REGISTRY: dict[str, EvidenceBuilder] | None = None


def get_evidence_builder(code: str) -> EvidenceBuilder | None:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY.get(code)
