"""Скрытая дорожка (E-серия) — пасхалки взаимодействия.

Отличие от `eggs.py`: там всё считается из БД по факту добавления пластинки,
здесь — реакция на ЖЕСТЫ. Половина этих жестов в БД следов не оставляет (тапы
по спиннеру, pull-to-refresh, промах распознавания), поэтому приходит клиентским
событием через allow-list `CLIENT_EVENTS` в `api/achievements.py`.

Состояние между событиями живёт в `UserAchievement.ach_metadata` — стрик сканов,
времена смены аватара, счётчик add/remove по релизу. Именно ради этих пасхалок
`_persist` умеет писать metadata и для ещё не открытой ачивки: без этого счётчик
терялся бы между запросами.

Контракт серии тот же, что у остальных пасхалок: `series="random"`, скрытые,
🌸 и выше, без счётчиков и подсказок в UI. Префикс `E_` (egg), чтобы не путать с
серией H (дискография).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user import User
from app.services.achievements.events import (
    ACHIEVEMENTS_OPENED,
    AVATAR_SET,
    COLLECTION_ITEM_ADDED,
    COLLECTION_ITEM_REMOVED,
    DAILY_TICK,
    PULLED_78,
    SCAN_ADDED,
    SCAN_MISS_MANUAL_ADD,
    VINYL_SPUN_33,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)
from app.services.vinyl_color import color_family

E_GLASS_EYE = "E_glass_eye"
E_DIGITIZER = "E_digitizer"
E_GLOW = "E_glow"
E_SPIN = "E_spin"
E_RAINBOW = "E_rainbow"
E_SECOND_THOUGHTS = "E_second_thoughts"
E_PHOTO_SHY = "E_photo_shy"
E_ANNIVERSARY = "E_anniversary"
E_PULL_78 = "E_pull_78"

#: Сколько подряд сканов держит «Оцифровщика».
DIGITIZER_STREAK = 10
#: Сколько разных цветов винила нужно для «Радуги».
RAINBOW_COLORS = 6
#: Сколько раз одну и ту же пластинку надо добавить-удалить.
SECOND_THOUGHTS_CYCLES = 3
#: Сколько смен аватара за сутки ловит «Не ту фотку».
PHOTO_SHY_CHANGES = 5
#: Окно годовщины регистрации, ±дней.
ANNIVERSARY_WINDOW_DAYS = 1

#: Чёрный — это не «цветной винил», иначе «Радуга» открывалась бы обычной полкой.
_RAINBOW_EXCLUDED_FAMILIES = {"black"}


# --- Общие помощники ---------------------------------------------------------

async def _user_record_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """id всех записей в коллекциях юзера."""
    rows = await db.execute(
        select(CollectionItem.record_id)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .where(Collection.user_id == user_id)
    )
    return list(rows.scalars().all())


def _meta(payload: dict[str, Any] | None, key: str, default: Any) -> Any:
    """Значение из metadata предыдущего прогона (его кладёт evaluator сам)."""
    if not isinstance(payload, dict):
        return default
    value = payload.get(key)
    return default if value is None else value


async def _load_meta(db: AsyncSession, user_id: UUID, code: str) -> dict[str, Any]:
    """Состояние пасхалки из БД. Пусто — значит жест случился впервые."""
    from app.models.user_achievement import UserAchievement

    row = await db.scalar(
        select(UserAchievement.ach_metadata).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code == code,
        )
    )
    return dict(row) if isinstance(row, dict) else {}


# --- Глаз-алмаз --------------------------------------------------------------

async def _evaluate_glass_eye(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """Скан не узнал обложку, а юзер добавил тот же релиз руками.

    Обе половины видит только клиент: бэкенд по отдельности видит неудачный
    поиск и обычное добавление, но не связь между ними. Поэтому событие
    приходит уже «сложенным».
    """
    return EvalResult(unlocked=True)


# --- Оцифровщик --------------------------------------------------------------

async def _evaluate_digitizer(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """10 пластинок подряд добавлены сканом.

    Стрик держим сами: клиент шлёт `scan_added` на каждое добавление сканом, а
    любое добавление БЕЗ скана (`collection_item_added` без пометки) обнуляет
    счётчик. Иначе «подряд» превратилось бы в «десять раз когда-нибудь».
    """
    meta = await _load_meta(db, user_id, E_DIGITIZER)
    streak = int(_meta(meta, "streak", 0))

    if _meta(payload, "via_scan", False):
        streak += 1
    else:
        streak = 0

    if streak >= DIGITIZER_STREAK:
        return EvalResult(unlocked=True, metadata={"streak": streak})
    return EvalResult(progress=streak, progress_target=DIGITIZER_STREAK,
                      metadata={"streak": streak})


# --- Светится в темноте ------------------------------------------------------

async def _evaluate_glow(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """В коллекции есть glow-in-the-dark винил.

    Цвет лежит в `Record.discogs_data->>'vinyl_color_raw'` (formats[0].text из
    Discogs), отдельной колонки под него нет. `color_family()` тут не помощник:
    «glow» — не семья цвета, а свойство, поэтому матчим подстроку.
    """
    hit = await db.scalar(
        select(func.count())
        .select_from(CollectionItem)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            Collection.user_id == user_id,
            Record.discogs_data["vinyl_color_raw"].astext.ilike("%glow%"),
        )
    )
    return EvalResult(unlocked=bool(hit))


# --- Закрутил ----------------------------------------------------------------

async def _evaluate_spin(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """33 тапа по спиннеру на ОДНОЙ карточке. Счёт ведёт клиент, он же и шлёт."""
    return EvalResult(unlocked=True)


# --- Радуга ------------------------------------------------------------------

async def _evaluate_rainbow(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """6+ цветных винилов разных цветов.

    Сырой цвет с Discogs грязный («Red Translucent», «180 Gram», «Gatefold»),
    поэтому считаем не строки, а семьи из `color_family()`: она отбрасывает вес
    и упаковку. Чёрный не в счёт — иначе «Радуга» открывалась бы обычной полкой.
    """
    rows = await db.execute(
        select(Record.discogs_data["vinyl_color_raw"].astext)
        .select_from(CollectionItem)
        .join(Collection, Collection.id == CollectionItem.collection_id)
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            Collection.user_id == user_id,
            Record.discogs_data["vinyl_color_raw"].astext.isnot(None),
        )
    )
    families = {
        family
        for raw in rows.scalars().all()
        if (family := color_family(raw)) and family not in _RAINBOW_EXCLUDED_FAMILIES
    }
    return EvalResult(
        unlocked=len(families) >= RAINBOW_COLORS,
        progress=min(len(families), RAINBOW_COLORS),
        progress_target=RAINBOW_COLORS,
    )


# --- Сомнения ----------------------------------------------------------------

async def _evaluate_second_thoughts(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """Одну и ту же пластинку добавил и удалил 3 раза.

    Считаем удаления по релизу: удалить можно только то, что до этого добавил,
    так что цикл «добавил-удалил» однозначно отмеряется удалением. Строка в БД
    к моменту события уже стёрта, поэтому record_id приходит в payload.
    """
    record_id = _meta(payload, "record_id", None)
    if not record_id:
        return EvalResult()

    meta = await _load_meta(db, user_id, E_SECOND_THOUGHTS)
    cycles: dict[str, int] = dict(_meta(meta, "cycles", {}))
    cycles[str(record_id)] = int(cycles.get(str(record_id), 0)) + 1

    # Держим только «горячие» релизы: без обрезки metadata растёт с каждым
    # удалением в коллекции и однажды раздувает строку.
    top = dict(sorted(cycles.items(), key=lambda kv: kv[1], reverse=True)[:50])
    best = max(top.values(), default=0)

    if best >= SECOND_THOUGHTS_CYCLES:
        return EvalResult(unlocked=True, metadata={"cycles": top})
    return EvalResult(
        progress=best, progress_target=SECOND_THOUGHTS_CYCLES, metadata={"cycles": top}
    )


# --- Не та фотка -------------------------------------------------------------

async def _evaluate_photo_shy(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """5 смен аватара за сутки.

    `AVATAR_SET` — единственный след смены аватара, история нигде не пишется,
    поэтому таймстемпы копим сами и на каждом событии выбрасываем всё старше
    суток. Скользящее окно, а не календарный день: пять смен подряд ночью через
    полночь — это ровно тот же случай.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=1)

    meta = await _load_meta(db, user_id, E_PHOTO_SHY)
    stamps: list[str] = list(_meta(meta, "stamps", []))
    stamps.append(now.isoformat())

    fresh = [s for s in stamps if _parse_iso(s) and _parse_iso(s) > cutoff]
    # Кап на случай мусора в metadata: больше окна нам всё равно не нужно.
    fresh = fresh[-PHOTO_SHY_CHANGES * 2:]

    if len(fresh) >= PHOTO_SHY_CHANGES:
        return EvalResult(unlocked=True, metadata={"stamps": fresh})
    return EvalResult(
        progress=len(fresh), progress_target=PHOTO_SHY_CHANGES, metadata={"stamps": fresh}
    )


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# --- Год спустя --------------------------------------------------------------

async def _evaluate_anniversary(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """Зашёл в «Ачивки» в годовщину регистрации (±1 день).

    Сравниваем день и месяц, а не «365 дней назад»: на второй и третий год
    ачивка должна ловиться так же. Високосное 29 февраля обслуживаем 28-м —
    иначе зарегистрировавшийся в этот день ждал бы четыре года.
    """
    created = await db.scalar(select(User.created_at).where(User.id == user_id))
    if created is None:
        return EvalResult()

    now = datetime.utcnow()
    if now.year <= created.year:
        return EvalResult()

    day = created.day
    if created.month == 2 and created.day == 29 and not _is_leap(now.year):
        day = 28
    try:
        anniversary = created.replace(year=now.year, day=day)
    except ValueError:
        return EvalResult()

    delta = abs((now.date() - anniversary.date()).days)
    return EvalResult(unlocked=delta <= ANNIVERSARY_WINDOW_DAYS)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


# --- Заело -------------------------------------------------------------------

async def _evaluate_pull_78(
    db: AsyncSession, user_id: UUID, payload: dict[str, Any] | None, unlocked_now: set[str]
) -> EvalResult:
    """78 pull-to-refresh за сессию. Счёт ведёт клиент — сессия есть только у него."""
    return EvalResult(unlocked=True)


# --- Определения -------------------------------------------------------------

def _egg(code, title, desc, tier, triggers, evaluator, flavor, slug):
    return AchievementDefinition(
        code=code, title_ru=title, description_ru=desc, series="random",
        tier=tier, is_hidden=True, triggers=triggers, evaluator=evaluator,
        flavor_ru=flavor, icon_slug=slug,
    )


DEFINITIONS: list[AchievementDefinition] = [
    _egg(E_GLASS_EYE, "Глаз-алмаз",
         "Камера не узнала обложку, а ты узнал.",
         AchievementTier.RARE, (SCAN_MISS_MANUAL_ADD,), _evaluate_glass_eye,
         "Машина сдалась. Ты — нет.", "e_glass_eye"),
    _egg(E_DIGITIZER, "Оцифровщик",
         "Десять пластинок подряд добавлены сканом.",
         AchievementTier.RARE, (SCAN_ADDED, COLLECTION_ITEM_ADDED), _evaluate_digitizer,
         "Полка переезжает в телефон.", "e_digitizer"),
    _egg(E_GLOW, "Светится в темноте",
         "В коллекции есть glow-in-the-dark винил.",
         AchievementTier.RARE, (COLLECTION_ITEM_ADDED, DAILY_TICK), _evaluate_glow,
         "Выключи свет. Он ещё играет.", "e_glow"),
    _egg(E_SPIN, "Закрутил",
         "Раскрутил пластинку на карточке 33 раза.",
         AchievementTier.RARE, (VINYL_SPUN_33,), _evaluate_spin,
         "Тридцать три оборота. Совпадение? Нет.", "e_spin"),
    _egg(E_RAINBOW, "Радуга",
         "Шесть цветных винилов разных цветов.",
         AchievementTier.RARE, (COLLECTION_ITEM_ADDED, DAILY_TICK), _evaluate_rainbow,
         "Полка перестала быть чёрной.", "e_rainbow"),
    _egg(E_SECOND_THOUGHTS, "Сомнения",
         "Одну и ту же пластинку добавил и удалил трижды.",
         AchievementTier.RARE, (COLLECTION_ITEM_REMOVED,), _evaluate_second_thoughts,
         "Всё ещё думаешь.", "e_second_thoughts"),
    _egg(E_PHOTO_SHY, "Не та фотка",
         "Сменил аватар пять раз за сутки.",
         AchievementTier.RARE, (AVATAR_SET,), _evaluate_photo_shy,
         "Ни одна не та.", "e_photo_shy"),
    _egg(E_ANNIVERSARY, "Год спустя",
         "Зашёл в «Ачивки» в годовщину регистрации.",
         AchievementTier.EPIC, (ACHIEVEMENTS_OPENED,), _evaluate_anniversary,
         "Ровно год назад ты нажал «Создать аккаунт».", "e_anniversary"),
    _egg(E_PULL_78, "Заело",
         "78 обновлений списка за одну сессию.",
         AchievementTier.RARE, (PULLED_78,), _evaluate_pull_78,
         "78 оборотов в минуту. Как в тридцатые.", "e_pull_78"),
]
