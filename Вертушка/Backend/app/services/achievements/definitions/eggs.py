"""Пасхалки второй волны: время, носители, платформа.

Держим отдельно от `random.py`, чтобы тот не разросся: там первая волна
(числовые и самореферентные), здесь — всё остальное, что считается на сервере
без новых событий с клиента.

Общий контракт пасхалок: скрытые, без счётчиков и подсказок, серия `random`.
Тир 🌸 и выше — как договорено в PLAN_ACHIEVEMENTS_V2 §5.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.offer_click import OfferClick
from app.models.record import Record
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import (
    COLLECTION_ITEM_ADDED,
    DAILY_TICK,
    OFFER_CLICKED,
)
from app.services.achievements.media_format import (
    BOX_SET,
    CASSETTE,
    CD,
    VINYL,
    parse_media,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)

R_SIXTY_NINE = "R_sixty_nine"
R_TIME_MACHINE_50 = "R_time_machine_50"
R_NEW_YEAR = "R_new_year"
R_FRIDAY_NIGHT = "R_friday_night"
R_LEAP_DAY = "R_leap_day"

R_THREE_LIVES = "R_three_lives"
R_TAPEHEAD = "R_tapehead"
R_CD_RENAISSANCE = "R_cd_renaissance"
R_TABLETOP_GIANT = "R_tabletop_giant"
R_TYPE_IV = "R_type_iv"
R_LIMITED_BOX = "R_limited_box"
R_HIDDEN_TRACK = "R_hidden_track"

MX_NIGHT_CRATE = "MX_night_crate"

#: Маркеры скрытого трека в названии. Ненумерованный трек ловится отдельно.
#: «bonus» здесь не место: обычный пронумерованный бонус-трек переиздания —
#: это не скрытый трек, а токен матчил бы половину каталога.
_HIDDEN_TITLE_TOKENS = (
    "hidden", "untitled", "secret",
    "скрыт", "без названия",
)

EXACT_COUNT_COOLDOWN = timedelta(hours=24)
TAPEHEAD_MIN = 10
CD_RENAISSANCE_MIN = 50
GIANT_BOX_DISCS = 10


async def _main_collection_items(db: AsyncSession, user_id: UUID, *, limit: int = 3000):
    """Записи основной коллекции: (record, added_at). Дедуп по record_id."""
    default_collection_id = (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Record, CollectionItem.added_at)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(CollectionItem.collection_id == default_collection_id)
        .limit(limit)
    )
    seen: set = set()
    out = []
    for record, added_at in rows.all():
        if record.id in seen:
            continue
        seen.add(record.id)
        out.append((record, added_at))
    return out


# --- Время -------------------------------------------------------------------

def _make_exact_count(target: int):
    """Ровно N пластинок и сутки тишины — юзер остановился, а не идёт дальше."""

    async def evaluator(db, user_id, payload, unlocked_now) -> EvalResult:
        row = await db.execute(
            select(
                func.count(func.distinct(CollectionItem.record_id)),
                func.max(CollectionItem.added_at),
            )
            .join(Collection, CollectionItem.collection_id == Collection.id)
            .where(Collection.user_id == user_id)
        )
        count, last_added = row.one()
        if int(count or 0) != target or last_added is None:
            return EvalResult()
        if datetime.utcnow() - last_added < EXACT_COUNT_COOLDOWN:
            return EvalResult()
        return EvalResult(unlocked=True)

    return evaluator


async def _evaluate_time_machine_50(db, user_id, payload, unlocked_now) -> EvalResult:
    """Пластинка года Y добавлена в год Y+50 (±30 дней от точной даты)."""
    for record, added_at in await _main_collection_items(db, user_id):
        if not record.year or added_at is None:
            continue
        if added_at.year - record.year != 50:
            continue
        return EvalResult(unlocked=True)
    return EvalResult()


def _make_added_at_rule(predicate):
    async def evaluator(db, user_id, payload, unlocked_now) -> EvalResult:
        for _record, added_at in await _main_collection_items(db, user_id):
            if added_at is not None and predicate(added_at):
                return EvalResult(unlocked=True)
        return EvalResult()

    return evaluator


def _is_new_year_moment(dt: datetime) -> bool:
    return dt.month == 1 and dt.day == 1 and dt.hour == 0 and dt.minute < 30


def _is_friday_night(dt: datetime) -> bool:
    # Пятница 22:00–23:59 либо ночь субботы 00:00–01:59.
    if dt.weekday() == 4 and dt.hour >= 22:
        return True
    return dt.weekday() == 5 and dt.hour < 2


def _is_leap_day(dt: datetime) -> bool:
    return dt.month == 2 and dt.day == 29


# --- Носители ----------------------------------------------------------------

async def _media_list(db: AsyncSession, user_id: UUID):
    return [
        (record, parse_media(record.format_type, record.format_description))
        for record, _added in await _main_collection_items(db, user_id)
    ]


async def _evaluate_three_lives(db, user_id, payload, unlocked_now) -> EvalResult:
    """Один и тот же альбом на виниле, CD и кассете.

    Группируем по мастеру, а при его отсутствии — по паре «артист + название»:
    у ручных релизов discogs_master_id пуст, и без фолбэка ачивка им недоступна.
    """
    by_album: dict[tuple, set[str]] = {}
    for record, info in await _media_list(db, user_id):
        key = (
            ("master", record.discogs_master_id)
            if record.discogs_master_id
            else ("title", (record.artist or "").lower(), (record.title or "").lower())
        )
        by_album.setdefault(key, set()).update(info.families)
    need = {VINYL, CD, CASSETTE}
    return EvalResult(unlocked=any(need <= fams for fams in by_album.values()))


async def _evaluate_tapehead(db, user_id, payload, unlocked_now) -> EvalResult:
    """Кассет больше, чем винила (при ≥10 кассетах)."""
    media = await _media_list(db, user_id)
    tapes = sum(1 for _r, i in media if i.has(CASSETTE))
    vinyls = sum(1 for _r, i in media if i.has(VINYL))
    return EvalResult(unlocked=tapes >= TAPEHEAD_MIN and tapes > vinyls)


async def _evaluate_cd_renaissance(db, user_id, payload, unlocked_now) -> EvalResult:
    """50+ компактов при наличии винила — CD не вторичны."""
    media = await _media_list(db, user_id)
    cds = sum(1 for _r, i in media if i.has(CD))
    has_vinyl = any(i.has(VINYL) for _r, i in media)
    return EvalResult(unlocked=cds >= CD_RENAISSANCE_MIN and has_vinyl)


async def _evaluate_tabletop_giant(db, user_id, payload, unlocked_now) -> EvalResult:
    """Бокс-сет с 10+ дисками внутри."""
    for _record, info in await _media_list(db, user_id):
        if info.has(BOX_SET) and info.qty >= GIANT_BOX_DISCS:
            return EvalResult(unlocked=True)
    return EvalResult()


async def _evaluate_type_iv(db, user_id, payload, unlocked_now) -> EvalResult:
    """Кассета с плёнкой Type IV / Metal."""
    return EvalResult(
        unlocked=any(info.is_type_iv for _r, info in await _media_list(db, user_id))
    )


async def _evaluate_limited_box(db, user_id, payload, unlocked_now) -> EvalResult:
    """Лимитированный / нумерованный / юбилейный бокс-сет."""
    for _record, info in await _media_list(db, user_id):
        if info.has(BOX_SET) and info.is_limited:
            return EvalResult(unlocked=True)
    return EvalResult()


async def _evaluate_hidden_track(db, user_id, payload, unlocked_now) -> EvalResult:
    """Издание со скрытым треком.

    План предлагал сравнивать «число треков > заявленного», но заявленного
    количества в данных нет — Discogs отдаёт только сам треклист. Зато скрытый
    трек виден по форме записи: у него ПУСТАЯ позиция при НЕПУСТОЙ длительности
    (ненумерованный трек), либо название прямо помечено как hidden/untitled.
    Именно так лежат ранние прессы, где бонус спрятан в конце последней стороны.

    Длительность обязательна не случайно: в исторических Record.tracklist (и в
    дамповой таблице треклистов) лежат heading-строки Discogs — заголовки
    сторон и секций. У них позиция тоже пустая, но длительности нет, а у
    настоящего ненумерованного трека она обычно проставлена. Новые обогащения
    heading-строки уже фильтруют на парсе (см. discogs._parse_release_tracklist),
    но старые данные никто не перечитает — эвристика держит и их.
    """
    for record, _added in await _main_collection_items(db, user_id):
        for track in record.tracklist or []:
            if not isinstance(track, dict):
                continue
            title = (track.get("title") or "").strip()
            if not title:
                continue
            position = (track.get("position") or "").strip()
            duration = (track.get("duration") or "").strip()
            if not position and duration:
                return EvalResult(unlocked=True)
            low = title.lower()
            if any(token in low for token in _HIDDEN_TITLE_TOKENS):
                return EvalResult(unlocked=True)
    return EvalResult()


# --- Маркет ------------------------------------------------------------------

async def _evaluate_night_crate(db, user_id, payload, unlocked_now) -> EvalResult:
    """Переход в магазин между 03:00 и 04:00 — ночной диггинг."""
    hit = await db.scalar(
        select(func.count())
        .select_from(OfferClick)
        .where(
            OfferClick.user_id == user_id,
            func.extract("hour", OfferClick.created_at) == 3,
        )
    )
    return EvalResult(unlocked=bool(hit))


_ADD_TRIGGERS = (COLLECTION_ITEM_ADDED, DAILY_TICK)


def _egg(code, title, desc, tier, triggers, evaluator, flavor, slug):
    return AchievementDefinition(
        code=code, title_ru=title, description_ru=desc, series="random",
        tier=tier, is_hidden=True, triggers=triggers, evaluator=evaluator,
        flavor_ru=flavor, icon_slug=slug,
    )


DEFINITIONS: list[AchievementDefinition] = [
    # Время
    _egg(R_SIXTY_NINE, "Шестьдесят девять", "В коллекции ровно 69 пластинок.",
         AchievementTier.RARE, _ADD_TRIGGERS, _make_exact_count(69),
         "Nice.", "r_sixty_nine"),
    _egg(R_TIME_MACHINE_50, "Полвека спустя",
         "Пластинка добралась до тебя ровно через 50 лет после выхода.",
         AchievementTier.RARE, _ADD_TRIGGERS, _evaluate_time_machine_50,
         "Полвека в пути.", "r_time_machine_50"),
    _egg(R_NEW_YEAR, "Первая в году", "Первая пластинка года — в первые полчаса января.",
         AchievementTier.RARE, _ADD_TRIGGERS,
         _make_added_at_rule(_is_new_year_moment),
         "Куранты отбили, игла опустилась.", "r_new_year"),
    _egg(R_FRIDAY_NIGHT, "Пятничный спин", "Пластинка, добавленная поздним вечером пятницы.",
         AchievementTier.RARE, _ADD_TRIGGERS, _make_added_at_rule(_is_friday_night),
         "Неделя кончилась. Начинается сторона А.", "r_friday_night"),
    _egg(R_LEAP_DAY, "29 февраля", "Пластинка, добавленная в високосный день.",
         AchievementTier.EPIC, _ADD_TRIGGERS, _make_added_at_rule(_is_leap_day),
         "День, которого обычно нет.", "r_leap_day"),
    # Носители
    _egg(R_THREE_LIVES, "Три жизни", "Один альбом на виниле, CD и кассете.",
         AchievementTier.EPIC, _ADD_TRIGGERS, _evaluate_three_lives,
         "Одна музыка, три тела.", "r_three_lives"),
    _egg(R_TAPEHEAD, "Тру-кассетник", "Кассет в коллекции больше, чем винила.",
         AchievementTier.EPIC, _ADD_TRIGGERS, _evaluate_tapehead,
         "Плёнка победила.", "r_tapehead"),
    _egg(R_CD_RENAISSANCE, "Ренессанс CD", "50+ компактов рядом с винилом.",
         AchievementTier.RARE, _ADD_TRIGGERS, _evaluate_cd_renaissance,
         "Их рано списали.", "r_cd_renaissance"),
    _egg(R_TABLETOP_GIANT, "Гигант на столе", "Бокс-сет с десятью и более дисками.",
         AchievementTier.RARE, _ADD_TRIGGERS, _evaluate_tabletop_giant,
         "Он не помещается никуда.", "r_tabletop_giant"),
    _egg(R_TYPE_IV, "Type IV", "Кассета с металлической плёнкой.",
         AchievementTier.RARE, _ADD_TRIGGERS, _evaluate_type_iv,
         "Высший класс плёнки.", "r_type_iv"),
    _egg(R_LIMITED_BOX, "Лимитка", "Лимитированный или нумерованный бокс-сет.",
         AchievementTier.RARE, _ADD_TRIGGERS, _evaluate_limited_box,
         "Номер на коробке кое-что значит.", "r_limited_box"),
    _egg(R_HIDDEN_TRACK, "Спрятанный трек", "Издание, где есть трек без номера.",
         AchievementTier.RARE, _ADD_TRIGGERS, _evaluate_hidden_track,
         "В конце что-то есть. Просто дослушай.", "r_hidden_track"),
    # Маркет
    _egg(MX_NIGHT_CRATE, "Ночной диггинг", "Копался в предложениях между тремя и четырьмя ночи.",
         AchievementTier.RARE, (OFFER_CLICKED, DAILY_TICK), _evaluate_night_crate,
         "В это время находится самое интересное.", "mx_night_crate"),
]
