"""API ачивок (Phase 1)."""
from __future__ import annotations

from typing import Iterable
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
from app.schemas.achievement import (
    AchievementItem,
    AchievementSeriesItem,
    AchievementTierInfo,
    CatalogResponse,
    MyAchievementsResponse,
    RandomUnlockedResponse,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    all_definitions,
    get_definition,
)
from app.services.achievements.share_card import render_for_format


router = APIRouter()


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
        "description_ru": "Подписки и просмотры.",
        "icon_emoji": "👥",
    },
    "invitations": {
        "title_ru": "Глас наружу",
        "description_ru": "Реферальная цепочка.",
        "icon_emoji": "🗣",
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
        # Реферальной программы пока нет — серия «Глас наружу» скрыта из выдачи.
        if defn.series == "invitations":
            continue
        ua = by_code.get(defn.code)
        grouped.setdefault(defn.series, []).append((defn, ua))

    series_list: list[AchievementSeriesItem] = []
    for series_key, pairs in grouped.items():
        meta = _SERIES_META.get(series_key)
        if meta is None:
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
    random_unlocked = sum(
        1
        for d in defs
        if d.series == "random" and by_code.get(d.code) and by_code[d.code].is_unlocked
    )
    return MyAchievementsResponse(
        total=total,
        unlocked=unlocked,
        random_unlocked=random_unlocked,
        series=series,
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
        ua = by_code.get(defn.code)
        if not ua or not ua.is_unlocked:
            continue
        items.append(_build_item(defn, ua, hide_secret=False))
    items.sort(key=lambda it: it.unlocked_at or it.code, reverse=True)
    return RandomUnlockedResponse(items=items)


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
    random_unlocked = sum(
        1
        for d in defs
        if d.series == "random" and by_code.get(d.code) and by_code[d.code].is_unlocked
    )
    return MyAchievementsResponse(
        total=total,
        unlocked=unlocked,
        random_unlocked=random_unlocked,
        series=series,
    )
