"""Дозагрузка цен после импорта коллекции из Discogs.

Сторожим три вещи, каждая из которых уже была источником тихой поломки.

1. Цены НЕ берутся из локального дампа. В `discogs_releases_index` ценовых
   колонок нет — месячный XML-дамп Discogs содержит только каталожные поля,
   marketplace-статистика живёт исключительно в API. Если кто-то однажды
   допишет в обогащение из дампа ценовое поле, оно будет молча заполнять
   коллекции пустотой.

2. Запрос цен идёт под личным OAuth-токеном юзера. В этом весь смысл задачи:
   персональный бакет rate-limiter'а (60 req/min) вместо общего app-лимита.
   Потеря `creds` по дороге не сломает ни одного теста, кроме этого, — задача
   продолжит работать, просто выест лимит приложения.

3. Форма ответа Discogs. Он отдаёт цену то объектом {value, currency}, то
   голым числом, в зависимости от эндпоинта и наличия лотов.
"""
import pytest

from app.services import discogs_index
from app.tasks.discogs_tasks import _price_value


class TestDumpHasNoPrices:
    def test_enrich_sql_touches_no_price_columns(self):
        """UPDATE из дампа не трогает ценовые поля Record."""
        sql = str(discogs_index._ENRICH_FROM_DUMP_SQL).lower()
        for column in (
            "estimated_price_min",
            "estimated_price_median",
            "estimated_price_max",
            "price_currency",
            "estimated_price_rub",
        ):
            assert column not in sql, (
                f"{column} появилась в обогащении из дампа — но дамп цен не "
                f"содержит, поле заполнится пустотой"
            )

    @pytest.mark.asyncio
    async def test_non_numeric_ids_never_reach_db(self):
        """Ручные релизы (source='user') имеют нечисловой discogs_id.

        Их id не должен уезжать в запрос: колонка в дампе — BigInteger, и
        параметр-строка уронил бы весь батч импорта на приведении типа.
        """
        class _NoCallSession:
            async def execute(self, *a, **kw):
                raise AssertionError("execute не должен вызываться для пустого списка")

        assert await discogs_index.enrich_records_from_dump(
            _NoCallSession(), ["user-abc", "", None, "не-число"]
        ) == 0


class TestPriceValueShape:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ({"value": 12.5, "currency": "USD"}, 12.5),
            (12.5, 12.5),
            (None, None),
            ({}, None),
        ],
    )
    def test_unwraps_both_shapes(self, raw, expected):
        assert _price_value(raw) == expected


class TestUserCredsArePassed:
    @pytest.mark.asyncio
    async def test_stats_request_uses_user_bucket(self, monkeypatch):
        """_get_price_stats с creds уходит в личный бакет rate-limiter'а.

        Проверяем не факт передачи аргумента, а то, что он доезжает до `_get` —
        именно там creds превращаются в OAuth-подпись и ключ бакета.
        """
        from app.services.discogs import DiscogsService
        from app.services import discogs as discogs_module

        seen = {}

        async def fake_get(self, url, params=None, headers=None, priority=None, creds=None):
            seen["creds"] = creds
            return {"lowest_price": {"value": 9.99}}

        class _NoCache:
            async def get(self, *a, **kw):
                return None

            async def exists(self, *a, **kw):
                return False

            async def set(self, *a, **kw):
                return None

        monkeypatch.setattr(DiscogsService, "_get", fake_get)
        monkeypatch.setattr(discogs_module, "cache", _NoCache())

        creds = ("token-abc", "secret-xyz")
        result = await DiscogsService()._get_price_stats("12345", creds=creds)

        assert seen["creds"] == creds, (
            "creds не доехали до _get — запросы пойдут через общий app-бакет"
        )
        assert _price_value(result["lowest_price"]) == 9.99
