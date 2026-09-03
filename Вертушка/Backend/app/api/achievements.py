"""API ачивок (Phase 1)."""
from __future__ import annotations

import logging
from typing import Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.services.achievements.definitions.series.formats import GATE_CODE_BY_SERIES
from app.services.achievements.events import (
    ACHIEVEMENTS_OPENED,
    PRICE_DRAWER_OPENED,
    PULLED_78,
    SCAN_ADDED,
    SCAN_MISS_MANUAL_ADD,
    VINYL_SPUN_33,
)
from app.services.achievements.evaluator import emit_event
from app.services.achievements.evidence import evidence_text
from app.services.achievements.levels import counts_toward_level, weight_for_code
from app.schemas.achievement import (
    AchievementItem,
    AchievementSeriesItem,
    AchievementTierInfo,
    CatalogResponse,
    MyAchievementsResponse,
    PeerRandomUnlockedResponse,
    RandomUnlockedResponse,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    all_definitions,
    get_definition,
)
from app.services.achievements.share_card import render_for_format


logger = logging.getLogger(__name__)

router = APIRouter()

# Серии, для которых отсутствие записи в _SERIES_META — намеренное решение,
# а не забывчивость. Про них warning не пишем.
_META_LESS_BY_DESIGN = frozenset({"random"})


# --- Метаданные тиров и серий ---------------------------------------------

_TIER_INFO: dict[AchievementTier, AchievementTierInfo] = {
    AchievementTier.SIMPLE: AchievementTierInfo(
        key="simple", label_ru="Простая", color_hex="#A5C8E1"
    ),
    AchievementTier.NOTABLE: AchievementTierInfo(
        key="notable", label_ru="Заметная", color_hex="#5B7DD8"
    ),
    AchievementTier.RARE: AchievementTierInfo(
        key="rare", label_ru="Редкая", color_hex="#E89AC0"
    ),
    AchievementTier.EPIC: AchievementTierInfo(
        key="epic", label_ru="Эпическая", color_hex="#1B237D"
    ),
    AchievementTier.LEGEND: AchievementTierInfo(
        key="legend", label_ru="Легенда", color_hex="#0A0A1A"
    ),
}


_SERIES_META: dict[str, dict[str, str]] = {
    "foundation": {
        "title_ru": "Первые шаги",
        "description_ru": "Базовые возможности.",
        "icon_emoji": "🌱",
    },
    "origins": {
        "title_ru": "Истоки",
        "description_ru": "Те, кто был с самого начала.",
        "icon_emoji": "🏁",
    },
    "scale": {
        "title_ru": "Размер коллекции",
        "description_ru": "Рост коллекции.",
        "icon_emoji": "📚",
    },
    "rarity": {
        "title_ru": "Охота за редкостями",
        "description_ru": "Лимитки и редкости.",
        "icon_emoji": "💎",
    },
    "geography": {
        "title_ru": "Кругосветка",
        "description_ru": "Прессы со всего мира.",
        "icon_emoji": "🌍",
    },
    "eras": {
        "title_ru": "Машина времени",
        "description_ru": "Винил по эпохам.",
        "icon_emoji": "📅",
    },
    "genres": {
        "title_ru": "Жанры",
        "description_ru": "Ширина вкусов.",
        "icon_emoji": "🎼",
    },
    "gifts": {
        "title_ru": "Дарящая рука",
        "description_ru": "Подарки близким.",
        "icon_emoji": "🎁",
    },
    "community": {
        "title_ru": "Сообщество",
        "description_ru": "Подписки и общение.",
        "icon_emoji": "👥",
    },
    "contribution": {
        "title_ru": "Вклад",
        "description_ru": "Ценность для коммьюнити.",
        "icon_emoji": "🏗",
    },
    "invitations": {
        "title_ru": "Глас наружу",
        "description_ru": "Реферальная цепочка.",
        "icon_emoji": "🗣",
    },
    "market": {
        "title_ru": "Рыночный нюх",
        "description_ru": "Охота за предложениями.",
        "icon_emoji": "🛒",
    },
    "value": {
        "title_ru": "Стоимость коллекции",
        "description_ru": "Сколько стоит полка.",
        "icon_emoji": "💰",
    },
    "formats": {
        "title_ru": "Форматы",
        "description_ru": "Не только винил.",
        "icon_emoji": "🎚",
    },
    "cassettes": {
        "title_ru": "Кассеты",
        "description_ru": "Плёнка и перемотка карандашом.",
        "icon_emoji": "📼",
    },
    "cds": {
        "title_ru": "Компакт-диски",
        "description_ru": "Серебряная полка.",
        "icon_emoji": "💿",
    },
    "boxsets": {
        "title_ru": "Бокс-сеты",
        "description_ru": "Издания, которые не влезают на полку.",
        "icon_emoji": "📦",
    },
    "discography": {
        "title_ru": "Полная дискография",
        "description_ru": "Глубокие коллекции.",
        "icon_emoji": "🎚",
    },
}


# --- Хелперы ---------------------------------------------------------------

def _build_item(
    defn: AchievementDefinition,
    ua: UserAchievement | None,
    *,
    hide_secret: bool,
) -> AchievementItem:
    is_unlocked = bool(ua and ua.is_unlocked)
    progress = ua.progress if ua else 0
    progress_target = ua.progress_target if ua else 0
    # Если ачивка скрытая и ещё не открыта — клиенту не отдаём имя и описание.
    if hide_secret and defn.is_hidden and not is_unlocked:
        return AchievementItem(
            code=defn.code,
            title_ru=None,
            description_ru=None,
            description_done_ru=None,
            flavor_ru=None,
            icon_slug=None,
            series=defn.series,
            tier=_TIER_INFO[defn.tier],
            is_hidden=True,
            is_meta=defn.is_meta,
            is_unlocked=False,
            unlocked_at=None,
            progress=0,
            progress_target=0,
            xp=weight_for_code(defn.code),
        )
    return AchievementItem(
        code=defn.code,
        title_ru=defn.title_ru,
        description_ru=defn.description_ru,
        description_done_ru=defn.description_done_ru or None,
        flavor_ru=defn.flavor_ru or None,
        icon_slug=defn.icon_slug or None,
        series=defn.series,
        tier=_TIER_INFO[defn.tier],
        is_hidden=defn.is_hidden,
        is_meta=defn.is_meta,
        is_unlocked=is_unlocked,
        unlocked_at=ua.unlocked_at if ua else None,
        progress=progress,
        progress_target=progress_target,
        xp=(
            ua.xp_awarded
            if is_unlocked and ua is not None and ua.xp_awarded is not None
            else weight_for_code(defn.code)
        ),
        evidence_text=(
            evidence_text(ua.ach_metadata) if is_unlocked and ua is not None else None
        ),
    )


#: Ачивки без чистового пина — не показываем юзеру до релиза арта.
#: Прогресс по ним считается и пишется в БД как обычно: когда пин появится,
#: достаточно убрать код отсюда, и уже открытая ачивка проявится с историей.
#:
#: Как обновлять: файл пина кладётся в `Mobile/assets/achievements/designs/`
#: с именем `<icon_slug>.png` (= код в нижнем регистре, если не задан другой
#: slug), после чего код удаляется из этого набора. Бэкенд не видит папку
#: ассетов, поэтому список ведётся руками — сверяйся с ней, а не с памятью.
_NO_ART_CODES: frozenset[str] = frozenset({
    # Видимые в гриде
    "C1_limited_x5",
    "T3_tapes_x25",
    "FMT2_multiformat",
    "FMT3_all_formats",
    "META_eras",
    # Пасхалки: до анлока показывают яйцо, после — потребовали бы свой пин
    "E_glass_eye",
    "E_spin",
    "R_cd_renaissance",
    "R_friday_night",
    "R_leap_day",
    "R_limited_box",
    "R_long_title",
    "R_meta_vertushka",
    "R_new_year",
    "R_self_aware",
    "R_seventy_eight",
    "R_tabletop_giant",
    "R_tapehead",
    "R_time_machine_50",
    "R_type_iv",
})


def _count_random_unlocked(
    defs: Iterable[AchievementDefinition],
    by_code: dict[str, UserAchievement],
) -> int:
    """Сколько пасхалок открыто — ровно тех, что реально попадут в выдачу.

    Считается здесь, а не по месту, потому что счётчик обязан совпадать с
    длиной списка из `/me/random`: разошлись — и юзер видит «3 открыто» над
    двумя пинами. Любой новый фильтр добавлять сюда и туда одновременно.
    """
    return sum(
        1
        for d in defs
        if d.series == "random"
        and d.code not in _NO_ART_CODES
        and by_code.get(d.code)
        and by_code[d.code].is_unlocked
    )


def _group_series(
    defs: Iterable[AchievementDefinition],
    by_code: dict[str, UserAchievement],
    *,
    include_hidden: bool,
    hide_secret: bool,
) -> list[AchievementSeriesItem]:
    """Группирует ачивки по серии, исключая random если include_hidden=False."""
    grouped: dict[str, list[tuple[AchievementDefinition, UserAchievement | None]]] = {}
    for defn in defs:
        if defn.series == "random" and not include_hidden:
            continue
        # Скрытые ачивки НЕ-рандомных серий (напр. K5/K6 — просмотры профиля,
        # выпилены с v2.1) полностью убираем из грида и счётчиков, а не маскируем.
        if defn.is_hidden and defn.series != "random" and not include_hidden:
            continue
        # Реферальной программы пока нет — серия «Глас наружу» скрыта из выдачи.
        if defn.series == "invitations":
            continue
        # Нет чистового пина — ачивки в гриде нет вообще, вместе со счётчиками.
        if defn.code in _NO_ART_CODES:
            continue
        ua = by_code.get(defn.code)
        grouped.setdefault(defn.series, []).append((defn, ua))

    series_list: list[AchievementSeriesItem] = []
    for series_key, pairs in grouped.items():
        meta = _SERIES_META.get(series_key)
        if meta is None:
            # Серия зарегистрирована, но её забыли описать в _SERIES_META.
            # Молча пропустить нельзя: ачивки будут открываться, слать пуши и
            # копить XP, а секции в приложении не окажется — юзер получит
            # уведомление про ачивку, которой нигде не видно.
            if series_key not in _META_LESS_BY_DESIGN:
                logger.warning(
                    "achievements: серия '%s' не описана в _SERIES_META — "
                    "%d ачивок не попадут в каталог. Добавь запись в "
                    "_SERIES_META (app/api/achievements.py).",
                    series_key,
                    len(pairs),
                )
            continue
        # Полки форматов появляются только когда формат появился в коллекции:
        # пустая витрина «Кассеты 0/4» у виниловода — шум, а не цель. Ключ —
        # первая ачивка серии (T1/CD1/BX1), она и открывается первой кассетой.
        gate_code = GATE_CODE_BY_SERIES.get(series_key)
        if gate_code is not None and not include_hidden:
            gate = by_code.get(gate_code)
            if gate is None or not gate.is_unlocked:
                continue
        items = [_build_item(d, ua, hide_secret=hide_secret) for d, ua in pairs]
        unlocked_count = sum(1 for it in items if it.is_unlocked)
        series_list.append(
            AchievementSeriesItem(
                key=series_key,
                title_ru=meta["title_ru"],
                description_ru=meta["description_ru"],
                icon_emoji=meta["icon_emoji"],
                total=len(items),
                unlocked=unlocked_count,
                items=items,
            )
        )
    return series_list


async def _load_user_achievements(
    db: AsyncSession, user_id: UUID
) -> dict[str, UserAchievement]:
    result = await db.execute(
        select(UserAchievement).where(UserAchievement.user_id == user_id)
    )
    return {ua.code: ua for ua in result.scalars().all()}


# --- Эндпоинты -------------------------------------------------------------


def _score_from_rows(by_code: dict[str, UserAchievement]) -> int:
    """XP пользователя по уже загруженным строкам — без лишнего запроса.

    Считает по тому же правилу, что `levels.compute_score`, и по замороженному
    `xp_awarded`, если он есть.
    """
    total = 0
    for code, ua in by_code.items():
        if not ua.is_unlocked or not counts_toward_level(code):
            continue
        total += ua.xp_awarded if ua.xp_awarded is not None else weight_for_code(code)
    return total


@router.get("/me", response_model=MyAchievementsResponse)
async def get_my_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyAchievementsResponse:
    """Ачивки текущего пользователя.

    Возвращает серии (с прогрессом по каждой ачивке) и счётчик открытых
    рандомных (без названий — клиент покажет их в отдельной секции «Сюрпризы»
    через /me/random).
    """
    by_code = await _load_user_achievements(db, current_user.id)

    defs = all_definitions()
    series = _group_series(
        defs,
        by_code,
        include_hidden=False,
        hide_secret=True,
    )
    total = sum(s.total for s in series)
    unlocked = sum(s.unlocked for s in series)
    random_unlocked = _count_random_unlocked(defs, by_code)
    return MyAchievementsResponse(
        total=total,
        unlocked=unlocked,
        random_unlocked=random_unlocked,
        series=series,
        score=_score_from_rows(by_code),
    )


@router.get("/me/random", response_model=RandomUnlockedResponse)
async def get_my_random_unlocked(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RandomUnlockedResponse:
    """Список открытых пользователем рандомных ачивок (полностью раскрытых)."""
    by_code = await _load_user_achievements(db, current_user.id)
    items: list[AchievementItem] = []
    for defn in all_definitions():
        if defn.series != "random":
            continue
        if defn.code in _NO_ART_CODES:
            continue
        ua = by_code.get(defn.code)
        if not ua or not ua.is_unlocked:
            continue
        items.append(_build_item(defn, ua, hide_secret=False))
    items.sort(key=lambda it: it.unlocked_at or it.code, reverse=True)
    return RandomUnlockedResponse(items=items)


@router.get(
    "/by-username/{username}/random",
    response_model=PeerRandomUnlockedResponse,
)
async def get_peer_random_unlocked(
    username: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PeerRandomUnlockedResponse:
    """Пасхалки чужого профиля — только те, что смотрящий открыл и сам.

    Раскрывать чужой список целиком нельзя: названия пасхалок описывают
    действие, которым они открываются, и витрина превратилась бы в гайд. А
    вот пересечение безопасно — про эти ачивки смотрящий уже всё знает, зато
    капсула «🥚 Пасхалки · N» перестаёт быть мёртвой цифрой.
    """
    user = await db.scalar(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    theirs = await _load_user_achievements(db, user.id)
    mine = (
        theirs
        if user.id == current_user.id
        else await _load_user_achievements(db, current_user.id)
    )

    items: list[AchievementItem] = []
    hidden_count = 0
    for defn in all_definitions():
        if defn.series != "random":
            continue
        if defn.code in _NO_ART_CODES:
            continue
        ua = theirs.get(defn.code)
        if not ua or not ua.is_unlocked:
            continue
        my_row = mine.get(defn.code)
        if my_row and my_row.is_unlocked:
            item = _build_item(defn, ua, hide_secret=False)
            # Улику («за какую музыку получено») чужому не отдаём: коллекция
            # может быть скрыта настройкой show_collection, а улика назвала бы
            # из неё конкретную пластинку в обход этого.
            item.evidence_text = None
            items.append(item)
        else:
            hidden_count += 1
    items.sort(key=lambda it: it.unlocked_at or it.code, reverse=True)
    return PeerRandomUnlockedResponse(items=items, hidden_count=hidden_count)


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CatalogResponse:
    """Каталог всех видимых серий и ачивок (для онбординга/описаний).

    Скрытые рандомные показаны общим счётчиком, без названий.
    Прогресс по ачивкам — текущий, как в /me.
    """
    by_code = await _load_user_achievements(db, current_user.id)
    defs = all_definitions()
    series = _group_series(
        defs,
        by_code,
        include_hidden=False,
        hide_secret=True,
    )
    random_count = sum(1 for d in defs if d.series == "random")
    return CatalogResponse(series=series, random_count=random_count)


class AchievementStats(BaseModel):
    """Глобальная статистика по ачивке: сколько юзеров уже открыли."""
    code: str
    total_users: int               # всего активных юзеров на платформе
    unlocked_users: int            # из них открыли эту ачивку
    unlocked_pct: float            # 0.0–1.0 (для UI можно умножить на 100)


@router.get("/{code}/stats", response_model=AchievementStats)
async def get_achievement_stats(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AchievementStats:
    """Сколько юзеров открыли эту ачивку (для подсказки «N% уже открыли»).

    Условия:
    - Считаем только активных юзеров (User.is_active=true).
    - Считаем только реально открытые (is_unlocked=true).
    - Доступно любому залогиненному юзеру для всех неhidden-кодов. Hidden
      (random) тоже доступно, чтобы клиент мог показать stats после анлока.
    """
    defn = get_definition(code)
    if defn is None:
        raise HTTPException(status_code=404, detail="Ачивка не найдена")

    total_users = await db.scalar(
        select(func.count(User.id)).where(User.is_active.is_(True))
    ) or 0

    unlocked_users = await db.scalar(
        select(func.count(UserAchievement.id))
        .join(User, User.id == UserAchievement.user_id)
        .where(
            UserAchievement.code == code,
            UserAchievement.is_unlocked.is_(True),
            User.is_active.is_(True),
        )
    ) or 0

    pct = (unlocked_users / total_users) if total_users > 0 else 0.0
    return AchievementStats(
        code=code,
        total_users=int(total_users),
        unlocked_users=int(unlocked_users),
        unlocked_pct=round(pct, 4),
    )


@router.get("/me/share-card/{code}")
async def get_share_card(
    code: str,
    fmt: str = Query("stories", pattern="^(stories|feed|portrait)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Сгенерировать share-card PNG для своей открытой ачивки.

    fmt:
    - `stories` — 1080×1920 (Instagram Stories, TikTok)
    - `feed`    — 1080×1080 (Instagram Feed)
    - `portrait` — 1080×1350 (Instagram Portrait)
    """
    defn = get_definition(code)
    if defn is None:
        raise HTTPException(status_code=404, detail="Ачивка не найдена")

    ua = await db.scalar(
        select(UserAchievement).where(
            UserAchievement.user_id == current_user.id,
            UserAchievement.code == code,
        )
    )
    if not ua or not ua.is_unlocked:
        raise HTTPException(status_code=403, detail="Ачивка ещё не открыта")

    png_bytes = render_for_format(
        defn,
        username=current_user.username,
        unlocked_at=ua.unlocked_at,
        fmt=fmt,
        evidence_text=evidence_text(ua.ach_metadata),
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/by-username/{username}", response_model=MyAchievementsResponse)
async def get_achievements_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
) -> MyAchievementsResponse:
    """Публично-видимые ачивки пользователя (для in-app и web-профилей).

    Логика как у /me, но смотрим чужого юзера. Скрытые рандомные отдаём только
    общим счётчиком. L-категория (стоимость) в Phase 0 ещё не реализована.
    """
    user = await db.scalar(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден"
        )

    by_code = await _load_user_achievements(db, user.id)
    defs = all_definitions()
    series = _group_series(
        defs,
        by_code,
        include_hidden=False,
        hide_secret=True,
    )
    total = sum(s.total for s in series)
    unlocked = sum(s.unlocked for s in series)
    random_unlocked = _count_random_unlocked(defs, by_code)
    return MyAchievementsResponse(
        total=total,
        unlocked=unlocked,
        random_unlocked=random_unlocked,
        series=series,
        score=_score_from_rows(by_code),
    )


# ============================================================================
# Клиентские события
# ============================================================================

#: События, которые может прислать только приложение — в БД их следов нет.
#: Строгий allow-list: эндпоинт открыт наружу, и без него сюда прилетело бы
#: что угодно, включая события, которые бэкенд эмитит сам (и тогда ачивку
#: можно было бы выпросить запросом, не делая ничего).
CLIENT_EVENTS = {
    "price_drawer_opened": PRICE_DRAWER_OPENED,
    # Скрытая дорожка (E-серия): жесты, которых в БД не видно.
    "scan_added": SCAN_ADDED,
    "scan_miss_manual_add": SCAN_MISS_MANUAL_ADD,
    "vinyl_spun_33": VINYL_SPUN_33,
    "pulled_78": PULLED_78,
    "achievements_opened": ACHIEVEMENTS_OPENED,
}

#: Какие поля payload'а клиент вправе присылать для конкретного события.
#: Всё остальное отбрасываем: payload идёт прямиком в evaluator, и без белого
#: списка через него можно было бы подкрутить чужое состояние.
CLIENT_EVENT_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "scan_added": frozenset({"record_id"}),
}


class ClientEventRequest(BaseModel):
    event: str
    payload: dict[str, Any] | None = None


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def track_client_event(
    body: ClientEventRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Приложение сообщает о жесте, которого не видно в БД.

    Ответ всегда 204: неизвестное событие молча игнорируем, чтобы старые
    сборки клиента не получали ошибок на событиях, которых уже нет.
    """
    event = CLIENT_EVENTS.get(body.event)
    if event is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    allowed = CLIENT_EVENT_PAYLOAD_KEYS.get(body.event, frozenset())
    payload = {
        k: v for k, v in (body.payload or {}).items() if k in allowed
    }
    # scan_added — единственное событие серии E, где добавление пришло через
    # скан. Пометка нужна evaluator-у «Оцифровщика», чтобы отличить его от
    # обычного collection_item_added, который стрик обнуляет.
    if body.event == "scan_added":
        payload["via_scan"] = True

    await emit_event(db, current_user.id, event, payload or None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
