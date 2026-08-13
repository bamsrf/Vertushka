"""
Сопоставление добавленной в коллекцию пластинки с активной бронью подарка.

Зачем: даритель бронирует конкретную версию релиза из вишлиста, но дарит часто
другой прессинг того же альбома. Получатель сканирует штрих-код — пластинка
уезжает в коллекцию, а бронь при этом теряется (пункт вишлиста удалялся мимо
брони, и она навсегда зависала в BOOKED).

Здесь мы находим кандидата на «это тот самый подарок» и отдаём его клиенту,
чтобы он спросил у пользователя. Сами ничего не решаем: matched по мастеру и
тем более по названию — это гипотеза, а не факт.
"""
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.gift_booking import GiftBooking, GiftStatus
from app.models.record import Record
from app.models.wishlist import Wishlist, WishlistItem
from app.services.artist_name import clean_artist_name

# Уверенность матча — от точного к предположительному.
MATCH_EXACT = "exact"    # та же самая запись (record_id совпал)
MATCH_MASTER = "master"  # другой прессинг того же мастер-релиза Discogs
MATCH_FUZZY = "fuzzy"    # совпали артист + название; мастера нет ни у одной из сторон

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _normalize(value: str | None) -> str:
    """Схлопывает регистр, пунктуацию и лишние пробелы для fuzzy-сравнения."""
    if not value:
        return ""
    lowered = _PUNCT_RE.sub(" ", value.lower())
    return _SPACE_RE.sub(" ", lowered).strip()


@dataclass(frozen=True)
class GiftMatch:
    """Найденная бронь-кандидат вместе с пунктом вишлиста, который её держит."""
    booking: GiftBooking
    wishlist_item: WishlistItem
    match_kind: str


async def find_gift_match(
    db: AsyncSession,
    *,
    user_id,
    record: Record,
) -> GiftMatch | None:
    """
    Ищет активную бронь в вишлисте пользователя, под которую подходит `record`.

    Порядок: точное совпадение записи → тот же discogs_master_id → артист+название.
    Возвращает первого кандидата по этому приоритету или None.

    Броня считается кандидатом только в статусе BOOKED: PENDING ещё не прошла
    email-верификацию (дарителя могло и не быть), COMPLETED/CANCELLED уже
    отвязаны от пункта вишлиста.
    """
    result = await db.execute(
        select(WishlistItem)
        .join(Wishlist)
        .join(GiftBooking, GiftBooking.wishlist_item_id == WishlistItem.id)
        .where(
            Wishlist.user_id == user_id,
            GiftBooking.status == GiftStatus.BOOKED,
            GiftBooking.match_dismissed_at.is_(None),
        )
        .options(
            selectinload(WishlistItem.record),
            selectinload(WishlistItem.gift_booking),
        )
    )
    candidates = result.scalars().unique().all()
    if not candidates:
        return None

    target_master = (record.discogs_master_id or "").strip()
    target_artist = _normalize(clean_artist_name(record.artist))
    target_title = _normalize(record.title)

    by_master: WishlistItem | None = None
    by_fuzzy: WishlistItem | None = None

    for item in candidates:
        wished = item.record
        if wished is None:
            continue

        if wished.id == record.id:
            return GiftMatch(item.gift_booking, item, MATCH_EXACT)

        wished_master = (wished.discogs_master_id or "").strip()
        if by_master is None and target_master and wished_master == target_master:
            by_master = item
            continue

        # Fuzzy — только когда мастера не помогли: у разных прессингов одного
        # альбома он часто просто не заполнен.
        if by_fuzzy is None and target_artist and target_title:
            if (
                _normalize(clean_artist_name(wished.artist)) == target_artist
                and _normalize(wished.title) == target_title
            ):
                by_fuzzy = item

    if by_master is not None:
        return GiftMatch(by_master.gift_booking, by_master, MATCH_MASTER)
    if by_fuzzy is not None:
        return GiftMatch(by_fuzzy.gift_booking, by_fuzzy, MATCH_FUZZY)
    return None
