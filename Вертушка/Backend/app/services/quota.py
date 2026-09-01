"""
Дневные квоты на дорогие операции.

Существует ради одного сценария: распознавание обложки стоит реальных денег
за вызов, и один скрипт «сканирую всё подряд» превращается в счёт от OpenAI.
Два рубежа:

1. **Per-user** — режет конкретного абьюзера, не трогая остальных.
2. **Глобальный дневной потолок** — последняя линия перед разорительным
   счётом. При подходе к нему прилетает аларм, при исчерпании сканер
   отвечает 429 до полуночи UTC.

**Fail-open при недоступности Redis.** Считать нечем — значит не мешаем, но
шлём аларм: молча работать без квот опаснее, чем работать с ними. Redis
лежит редко, а сломанный на весь день сканер бьёт по всем пользователям.

См. docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.3.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_settings
from app.services import alerts
from app.services.cache import cache

logger = logging.getLogger(__name__)

_NAMESPACE = "quota"

# Доля глобального лимита, на которой предупреждаем. 0.8 = за час-два до
# исчерпания ещё можно среагировать.
_WARN_RATIO = 0.8

# Человек физически не сканирует чаще: навести камеру, дождаться ответа,
# посмотреть результат. Всё, что выше — скрипт.
_VISION_BURST_PER_MINUTE = 6


@dataclass(frozen=True)
class QuotaStatus:
    """Результат попытки списать квоту."""

    allowed: bool
    used: int
    limit: int
    retry_after_seconds: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def _today_key(scope: str, subject: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{scope}:{subject}:{day}"


def _seconds_until_utc_midnight() -> int:
    """TTL счётчика = остаток суток. Минимум 60с, чтобы ключ, созданный
    в 23:59:59, не протух мгновенно и не дал лишнюю попытку."""
    now = datetime.now(timezone.utc)
    seconds_today = now.hour * 3600 + now.minute * 60 + now.second
    return max(60, 24 * 3600 - seconds_today)


async def consume_daily(scope: str, subject: str, limit: int) -> QuotaStatus:
    """Списать одну единицу дневной квоты.

    Возвращает allowed=False, если лимит уже исчерпан. При недоступности
    Redis всегда allowed=True (fail-open, см. докстринг модуля).
    """
    ttl = _seconds_until_utc_midnight()
    used = await cache.incr(_NAMESPACE, _today_key(scope, subject), ttl=ttl)

    if used is None:
        alerts.fire_and_forget(
            key="quota_redis_down",
            title="Квоты не работают: Redis недоступен",
            body=f"scope={scope}. Дорогие операции сейчас без потолка.",
        )
        return QuotaStatus(allowed=True, used=0, limit=limit, retry_after_seconds=0)

    return QuotaStatus(
        allowed=used <= limit,
        used=used,
        limit=limit,
        retry_after_seconds=ttl if used > limit else 0,
    )


async def peek_daily(scope: str, subject: str) -> int:
    """Текущий расход без списания. 0 если Redis недоступен."""
    return await cache.get_counter(_NAMESPACE, _today_key(scope, subject)) or 0


async def consume_burst(scope: str, subject: str, per_minute: int) -> bool:
    """Защита от бёрста: не больше `per_minute` за скользящую минуту.

    Дневная квота не спасает от скрипта, который сожжёт её за 20 секунд и
    забьёт очередь к OpenAI. Считаем в Redis, а не в памяти процесса —
    иначе во время blue-green деплоя лимит удваивается.

    Fail-open при недоступности Redis (см. докстринг модуля).
    """
    wait_ms = await cache.take_token(
        f"{scope}:{subject}", capacity=per_minute, refill_rate_per_sec=0,
    )
    return wait_ms is None or wait_ms == 0


async def consume_vision_scan(user_id: str) -> QuotaStatus:
    """Квота на распознавание обложки: бёрст → пользователь → общий потолок.

    Порядок неслучаен. Глобальный счётчик инкрементируется последним, только
    когда запрос прошёл предыдущие рубежи — иначе отклонённые запросы жгли бы
    общий лимит и один абьюзер выключил бы сканер всем.
    """
    settings = get_settings()

    if not await consume_burst("vision_scan", str(user_id), _VISION_BURST_PER_MINUTE):
        logger.info("Vision: бёрст-лимит у пользователя %s", user_id)
        return QuotaStatus(
            allowed=False,
            used=_VISION_BURST_PER_MINUTE,
            limit=_VISION_BURST_PER_MINUTE,
            retry_after_seconds=60,
        )

    per_user = await consume_daily(
        "vision_scan", str(user_id), settings.vision_scan_daily_limit_per_user,
    )
    if not per_user.allowed:
        logger.info("Vision-квота исчерпана пользователем %s (%s)", user_id, per_user.used)
        return per_user

    return await _consume_vision_global(settings.vision_scan_daily_limit_global)


async def _consume_vision_global(limit: int) -> QuotaStatus:
    status = await consume_daily("vision_scan_global", "all", limit)

    # Строгое равенство: счётчик растёт по единице, поэтому каждый порог
    # пересекается ровно один раз и аларм не спамит.
    warn_at = int(limit * _WARN_RATIO)
    if status.used == warn_at:
        alerts.fire_and_forget(
            key="vision_quota_warn",
            title=f"Vision: израсходовано {warn_at} из {limit} за сутки",
            body="Осталось меньше четверти дневного потолка сканирований.",
        )
    elif status.used == limit + 1:
        alerts.fire_and_forget(
            key="vision_quota_exhausted",
            title="Vision: дневной потолок исчерпан, сканер отвечает 429",
            body=(
                f"Лимит {limit}/сутки. Сбросится в полночь UTC. "
                "Поднять: VISION_SCAN_DAILY_LIMIT_GLOBAL в .env."
            ),
        )

    return status
