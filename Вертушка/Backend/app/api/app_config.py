"""
Remote config API.

Публичный `GET /api/config` — force-update gate и kill-switch для клиента.
Staff-эндпоинты под `/api/admin/config` — мгновенный флип без деплоя.
См. docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.2.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.admin import require_staff
from app.config import get_settings
from app.models.user import User
from app.schemas.app_config import (
    AppConfigResponse,
    FlagsUpdateRequest,
    MinVersionUpdateRequest,
)
from app.services import app_config

logger = logging.getLogger(__name__)

router = APIRouter()
admin_router = APIRouter()

# Сообщение пользователю, когда фича выключена рубильником. Текст нейтральный:
# «временно недоступно» честнее, чем «ошибка», и не пугает.
_DISABLED_DETAIL = "Раздел временно недоступен. Мы уже занимаемся этим."

# Клиент ретраит 503 трижды с backoff (Mobile/lib/api.ts). Для выключенной
# рубильником фичи это бессмысленно: 7 секунд ожидания у пользователя и
# четырёхкратная нагрузка на эндпоинт, который мы только что погасили.
# Заголовок отличает «выключено осознанно» от «сервису плохо».
FEATURE_DISABLED_HEADER = "X-Feature-Disabled"


def require_flag(flag: str):
    """Фабрика зависимости: закрывает эндпоинт, когда флаг выключен.

    Использование: `dependencies=[Depends(require_flag("market"))]`
    Отдаёт 503 — это временная недоступность, а не ошибка клиента.
    """

    async def _guard() -> None:
        if not await app_config.is_enabled(flag):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_DISABLED_DETAIL,
                headers={FEATURE_DISABLED_HEADER: flag},
            )

    return _guard


@router.get("/", response_model=AppConfigResponse)
async def get_app_config():
    """Конфиг для клиента. Без авторизации — читается до логина.

    Клиент обязан обрабатывать недоступность этого эндпоинта как «всё
    разрешено» (fail-open): гейт, который блокирует пользователей при
    моргнувшей сети, хуже отсутствия гейта.
    """
    settings = get_settings()
    return AppConfigResponse(
        min_supported_version=await app_config.get_min_supported_version(),
        store_url=settings.app_store_url,
        update_message=settings.force_update_message,
        flags=await app_config.get_flags(),
    )


@admin_router.get("/", response_model=AppConfigResponse)
async def get_app_config_admin(_staff: User = Depends(require_staff)):
    """То же самое, но явно для проверки staff'ом после флипа."""
    return await get_app_config()


@admin_router.put("/flags/", response_model=AppConfigResponse)
async def update_flags(
    payload: FlagsUpdateRequest,
    staff: User = Depends(require_staff),
):
    """Kill-switch: выключить или включить фичу. Применяется за секунды."""
    try:
        await app_config.set_flags(payload.flags)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    logger.warning("Флаги изменены пользователем %s: %s", staff.id, payload.flags)
    return await get_app_config()


@admin_router.put("/min-version/", response_model=AppConfigResponse)
async def update_min_version(
    payload: MinVersionUpdateRequest,
    staff: User = Depends(require_staff),
):
    """Поднять минимальную версию — выгнать сломанный билд на обновление."""
    try:
        await app_config.set_min_supported_version(payload.version)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    logger.warning(
        "min_supported_version поднята пользователем %s: %s", staff.id, payload.version
    )
    return await get_app_config()


@admin_router.post("/reset/", response_model=AppConfigResponse)
async def reset_overrides(staff: User = Depends(require_staff)):
    """Сбросить рантайм-оверрайды к значениям из .env."""
    await app_config.clear_overrides()
    logger.warning("Оверрайды конфига сброшены пользователем %s", staff.id)
    return await get_app_config()
