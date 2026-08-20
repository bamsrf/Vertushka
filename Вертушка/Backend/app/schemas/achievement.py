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
    # Опыт за ачивку. Для открытой — ЗАМОРОЖЕННЫЙ (сколько дали в момент
    # анлока), для закрытой — сколько дадут сейчас. Клиент складывает уровень
    # из этих чисел, чтобы не расходиться с сервером при смене весов тиров.
    xp: int = 0
    # «За какую музыку получено» — короткий текст улики, замороженной в момент
    # анлока (только музыка, без людей). None — улики нет, строка не рисуется.
    evidence_text: str | None = None


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
    # Суммарный XP по ачивкам, идущим в зачёт уровня (включая пасхалки).
    # Считает сервер: клиент видит не все ачивки сразу (пасхалки приходят
    # отдельным запросом), и складывая сам, он расходился бы с пушем.
    score: int = 0



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
