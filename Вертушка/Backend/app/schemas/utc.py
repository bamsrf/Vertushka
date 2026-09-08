"""
Даты в API-ответах — всегда с офсетом.

В БД колонки `DateTime` без tz, модели пишут туда naive `datetime.utcnow()`.
Pydantic сериализует naive datetime как `2026-09-08T12:00:00` — без `Z`,
и Hermes на обеих платформах парсит такую строку как ЛОКАЛЬНОЕ время:
в Europe/Moscow «минуту назад» превращается в «3 ч назад» (BUGS A14).

Хранение не трогаем (сравнения с `utcnow()` в коде остаются naive), чиним
только выход: `UtcDatetime` навешивает UTC на naive значение при сериализации,
`utc_isoformat` — то же для ручных `isoformat()` в WS-событиях и dict-ответах.
"""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def as_utc(value: datetime) -> datetime:
    """Naive datetime трактуем как UTC; aware — отдаём как есть."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def utc_isoformat(value: datetime | None) -> str | None:
    """ISO-строка с офсетом (`+00:00`) для ручной сборки JSON/WS-событий."""
    if value is None:
        return None
    return as_utc(value).isoformat()


# В JSON pydantic отдаёт aware-UTC как `...Z` — клиент парсит однозначно.
UtcDatetime = Annotated[datetime, PlainSerializer(as_utc, return_type=datetime)]
