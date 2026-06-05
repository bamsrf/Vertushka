"""Pydantic-схемы для API ачивок."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AchievementTierInfo(BaseModel):
    """Информация о тире для UI."""
    key: str          # 'simple' | 'notable' | 'rare' | 'epic' | 'legend'
    label_ru: str     # 'Простая' | 'Заметная' | ...
    color_hex: str    # #A5C8E1 и т.д.


class AchievementItem(BaseModel):
    """Одна ачивка в ответе API.

    Если `is_hidden=true` и `is_unlocked=false` — клиент рисует слот как
    «❓ Сюрприз», название/описание не показывает.
    """
    code: str
    title_ru: str | None = None
    description_ru: str | None = None
    description_done_ru: str | None = None  # прошедшее время для открытой ачивки
    flavor_ru: str | None = None
    icon_slug: str | None = None
    series: str
    tier: AchievementTierInfo
    is_hidden: bool
    is_meta: bool
    is_unlocked: bool
    unlocked_at: datetime | None = None
    progress: int = 0
    progress_target: int = 0


class AchievementSeriesItem(BaseModel):
    """Группировка ачивок по серии для UI."""
    key: str
    title_ru: str
    description_ru: str
    icon_emoji: str
    total: int
    unlocked: int
    items: list[AchievementItem]


class MyAchievementsResponse(BaseModel):
    """Ответ GET /api/achievements/me."""
    total: int
    unlocked: int
    random_unlocked: int   # количество открытых рандомных (без названий)
    series: list[AchievementSeriesItem]


class CatalogResponse(BaseModel):
    """Ответ GET /api/achievements/catalog.

    Каталог видимых серий и ачивок (для онбординга / описаний). Рандомные
    представлены только общим счётчиком, без названий.
    """
    series: list[AchievementSeriesItem]
    random_count: int  # сколько всего скрытых ачивок (для подзаголовка «❓ Сюрпризы»)


class RandomUnlockedResponse(BaseModel):
    """Ответ GET /api/achievements/me/random — только полученные рандомные."""
    items: list[AchievementItem]
