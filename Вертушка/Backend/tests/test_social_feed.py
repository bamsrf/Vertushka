"""Лента подписок: сборка запросов ко всем источникам событий.

Прод-инцидент 2026-09-09: `GET /api/notifications/social` отдавал 500 с
`AttributeError: type object 'GiftBooking' has no attribute 'updated_at'`.
Колонки не было никогда — обращение к ней падало при СБОРКЕ запроса, ещё до
похода в базу, то есть у каждого, у кого есть хоть одна подписка. У кого
подписок нет, функция выходит раньше, поэтому баг прожил четыре месяца
(с 42a92a1 от 17.05.2026) и всплыл, только когда кто-то открыл вкладку.

Отсюда два уровня защиты:

* `TestQueryBuild` прогоняет get_social_feed целиком на сессии-заглушке. БД
  не нужна: любая опечатка в имени колонки роняет тест на построении запроса
  — ровно там же, где ронялся прод.
* `TestModelAttributes` статически проверяет КАЖДОЕ обращение `Модель.поле`
  в feed.py. Это страховка от того же класса ошибки в источниках, до которых
  заглушка не доберётся, если однажды появится ранний выход.
"""
import ast
import inspect
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.services.feed import get_social_feed

FEED_PATH = Path("app/services/feed.py")


# ── Сессия-заглушка ─────────────────────────────────────────────────────────
# Возвращает подписки на первый execute и пустоту дальше. Смысл не в данных,
# а в том, что функция обязана дойти до конца, построив все запросы.

class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return _Scalars([r[0] for r in self._rows])


class _StubSession:
    def __init__(self, following_ids: list[UUID]):
        self._following_ids = following_ids
        self.statements: list[object] = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        if len(self.statements) == 1:
            return _Result([(i,) for i in self._following_ids])
        return _Result([])

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return None


class TestQueryBuild:
    async def test_feed_builds_every_query_for_a_user_with_subscriptions(self):
        """Регрессия на прод-500: падало здесь, на сборке gift_completed."""
        db = _StubSession([uuid4()])

        items, next_cursor = await get_social_feed(
            db, user_id=uuid4(), limit=20, cursor_iso=None,
        )

        assert items == []
        assert next_cursor is None
        assert len(db.statements) > 1, "источники событий не опрашивались"

    async def test_feed_builds_every_query_with_a_cursor(self):
        """Ветки `if cutoff is not None` — отдельный набор обращений к колонкам.

        Именно в такой ветке жила половина обращений к несуществующему полю,
        и первая страница ленты её не задевает.
        """
        db = _StubSession([uuid4()])
        cursor = (datetime.utcnow() - timedelta(days=1)).isoformat()

        items, next_cursor = await get_social_feed(
            db, user_id=uuid4(), limit=20, cursor_iso=cursor,
        )

        assert items == []
        assert next_cursor is None

    async def test_no_subscriptions_short_circuits(self):
        """Ранний выход — причина, по которой баг не замечали."""
        db = _StubSession([])

        items, next_cursor = await get_social_feed(
            db, user_id=uuid4(), limit=20, cursor_iso=None,
        )

        assert (items, next_cursor) == ([], None)
        assert len(db.statements) == 1


class TestModelAttributes:
    """Каждое `Модель.поле` в feed.py должно существовать на модели."""

    @staticmethod
    def _model_references() -> list[tuple[str, str, int]]:
        import app.services.feed as feed

        tree = ast.parse(FEED_PATH.read_text(encoding="utf-8"))
        models = {
            name: obj
            for name, obj in vars(feed).items()
            if inspect.isclass(obj) and hasattr(obj, "__mapper__")
        }
        assert models, "в feed.py не нашлось ни одной ORM-модели"

        found = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in models
            ):
                found.append((node.value.id, node.attr, node.lineno))
        return found

    def test_every_referenced_column_exists(self):
        import app.services.feed as feed

        missing = [
            f"feed.py:{lineno} — {model}.{attr}"
            for model, attr, lineno in self._model_references()
            if not hasattr(getattr(feed, model), attr)
        ]
        assert not missing, (
            "обращение к несуществующему полю модели: " + "; ".join(missing) +
            ". Падает при сборке запроса, в рантайме и только у части "
            "пользователей — см. прод-инцидент 2026-09-09."
        )

    def test_the_check_actually_sees_references(self):
        """Страховка от немого теста: сломанный парсер молчал бы точно так же."""
        refs = self._model_references()
        assert len(refs) > 10
        assert any(m == "GiftBooking" and a == "completed_at" for m, a, _ in refs), (
            "gift_completed больше не сортируется по completed_at — "
            "проверь, что тест всё ещё про то же"
        )
