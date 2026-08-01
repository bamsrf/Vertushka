"""
Remote config — force-update gate и kill-switch фич.

Зачем: выключить дорогую или сломанную фичу и поднять минимальную версию
приложения нужно за секунды, без деплоя и без нового ревью в App Store.
См. docs/plans/APPSTORE_LAUNCH_PLAN.md §4.2.

Слои значений (побеждает первый, у кого есть значение):
1. Redis — рантайм-оверрайд, ставится staff-эндпоинтом, применяется мгновенно
2. .env / settings — дефолт, переживает рестарт Redis

Redis-оверрайд живёт RUNTIME_OVERRIDE_TTL (90 дней). Если Redis потеряет
данные, конфиг откатится к env-дефолтам — то есть фича, выключенная только
через Redis, снова включится. Поэтому: выключил на инцидент через API →
если это надолго, продублируй в .env и выкати при ближайшем деплое.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.config import get_settings
from app.services.cache import cache

logger = logging.getLogger(__name__)

_NAMESPACE = "appcfg"
_FLAGS_KEY = "flags"
_MIN_VERSION_KEY = "min_version"

# 90 дней — оверрайд не должен протухать сам по себе посреди инцидента.
RUNTIME_OVERRIDE_TTL = 90 * 24 * 3600

# In-process кэш: /api/config дёргается на каждом холодном старте приложения,
# а флаги читаются на горячих путях. Ходить в Redis каждый раз не нужно.
_LOCAL_TTL_SECONDS = 5.0
_local_cache: dict[str, tuple[float, Any]] = {}


def _flag_env_defaults() -> dict[str, bool]:
    """Дефолты флагов из settings. Ключ = имя флага в API."""
    s = get_settings()
    return {
        # Распознавание обложки через GPT-4o Vision — самая дорогая операция.
        "vision_scan": s.feature_vision_scan_enabled,
        # Витрина маркета и карточки офферов (юр. риск по ToS магазинов).
        "market": s.feature_market_enabled,
        # Фоновый краулинг магазинов.
        "shop_scrapers": s.feature_shop_scrapers_enabled,
        # Добавление пользовательских пластинок (UGC).
        "user_submitted": s.feature_user_submitted_enabled,
    }


FLAG_NAMES = tuple(_flag_env_defaults().keys())


def _local_get(key: str) -> Any | None:
    entry = _local_cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _local_cache.pop(key, None)
        return None
    return value


def _local_set(key: str, value: Any) -> None:
    _local_cache[key] = (time.monotonic() + _LOCAL_TTL_SECONDS, value)


def _local_invalidate() -> None:
    _local_cache.clear()


async def get_flags() -> dict[str, bool]:
    """Актуальные значения всех флагов (Redis поверх env-дефолтов)."""
    cached = _local_get(_FLAGS_KEY)
    if cached is not None:
        return cached

    flags = _flag_env_defaults()
    override = await cache.get(_NAMESPACE, _FLAGS_KEY)
    if isinstance(override, dict):
        for name, value in override.items():
            if name in flags and isinstance(value, bool):
                flags[name] = value

    _local_set(_FLAGS_KEY, flags)
    return flags


async def is_enabled(flag: str) -> bool:
    """Проверка одного флага. Неизвестный флаг считается включённым."""
    if flag not in FLAG_NAMES:
        logger.warning("Проверка неизвестного флага: %s", flag)
        return True
    return (await get_flags())[flag]


async def set_flags(updates: dict[str, bool]) -> dict[str, bool]:
    """Записать рантайм-оверрайд флагов. Мержится с уже записанным."""
    unknown = set(updates) - set(FLAG_NAMES)
    if unknown:
        raise ValueError(f"Неизвестные флаги: {', '.join(sorted(unknown))}")

    current = await cache.get(_NAMESPACE, _FLAGS_KEY)
    merged: dict[str, bool] = dict(current) if isinstance(current, dict) else {}
    merged.update(updates)

    await cache.set(_NAMESPACE, _FLAGS_KEY, merged, ttl=RUNTIME_OVERRIDE_TTL)
    _local_invalidate()

    logger.warning("Флаги изменены через API: %s", updates)
    return await get_flags()


async def get_min_supported_version() -> str:
    """Минимальная версия приложения, которой разрешено работать."""
    cached = _local_get(_MIN_VERSION_KEY)
    if cached is not None:
        return cached

    override = await cache.get(_NAMESPACE, _MIN_VERSION_KEY)
    version = override if isinstance(override, str) and override else (
        get_settings().min_supported_app_version
    )

    _local_set(_MIN_VERSION_KEY, version)
    return version


async def set_min_supported_version(version: str) -> str:
    """Поднять минимальную версию без деплоя (аварийная кнопка)."""
    if not _is_valid_version(version):
        raise ValueError(f"Некорректная версия: {version!r}. Ожидается вид 1.2.3")

    await cache.set(_NAMESPACE, _MIN_VERSION_KEY, version, ttl=RUNTIME_OVERRIDE_TTL)
    _local_invalidate()

    logger.warning("min_supported_app_version поднята через API: %s", version)
    return version


async def clear_overrides() -> None:
    """Сбросить все рантайм-оверрайды к env-дефолтам."""
    await cache.delete(_NAMESPACE, _FLAGS_KEY)
    await cache.delete(_NAMESPACE, _MIN_VERSION_KEY)
    _local_invalidate()
    logger.warning("Рантайм-оверрайды конфига сброшены")


def _is_valid_version(version: str) -> bool:
    parts = version.split(".")
    if len(parts) != 3:
        return False
    return all(p.isdigit() for p in parts)
