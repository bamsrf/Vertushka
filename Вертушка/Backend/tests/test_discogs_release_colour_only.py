"""Узкий фетч цвета: один запрос к Discogs вместо трёх.

`get_release` попутно тянет статистику цен с маркетплейса и миниатюру артиста.
Карточке записи это нужно, ре-фетчу цвета — нет: втрое больше токенов из
бакета и втрое дольше. На боевом прогоне 12.09 вышло ~14 с/запись и пачка
429 именно на `marketplace/stats`, при том что для цвета хватает одного
GET /releases/{id}.

Тест держит ровно это свойство: лишние ручки не дёргаются.
"""
import pytest

from app.services.discogs import DiscogsService


class _Spy(DiscogsService):
    """Считает, какие URL пошли бы в сеть."""

    def __init__(self, payload):
        self.calls: list[str] = []
        self._payload = payload

    async def _get(self, url, *args, **kwargs):
        self.calls.append(url)
        if self._payload is None:
            raise RuntimeError("boom")
        return self._payload


@pytest.mark.asyncio
async def test_only_the_release_endpoint_is_called():
    """Ни marketplace/stats, ни artists/{id} — только сам релиз."""
    spy = _Spy({"formats": [{"name": "Vinyl", "text": "Red Translucent"}]})

    color = await spy.get_release_vinyl_color("123")

    assert color == "Red Translucent"
    assert len(spy.calls) == 1, spy.calls
    assert spy.calls[0].endswith("/releases/123")
    assert not any("marketplace" in u or "/artists/" in u for u in spy.calls)


@pytest.mark.asyncio
async def test_colour_is_parsed_with_the_fixed_parser():
    """Тот же разбор, что на записи: все форматы + отсев упаковки."""
    spy = _Spy({"formats": [
        {"name": "Vinyl", "text": "Gatefold"},
        {"name": "Vinyl", "text": "Gold Inner Sleeve"},
        {"name": "Box Set", "text": "Blue Marbled"},
    ]})

    assert await spy.get_release_vinyl_color("123") == "Blue Marbled"


@pytest.mark.asyncio
async def test_no_colour_is_none_not_an_error():
    """Discogs просто не знает цвета — это законный ответ, а не сбой."""
    spy = _Spy({"formats": [{"name": "Vinyl", "text": "180 Gram"}]})

    assert await spy.get_release_vinyl_color("123") is None


@pytest.mark.asyncio
async def test_missing_formats_key_is_survivable():
    spy = _Spy({"title": "X"})

    assert await spy.get_release_vinyl_color("123") is None


@pytest.mark.asyncio
async def test_network_failure_propagates():
    """Бросаем наверх: вызывающий обязан отличить сбой от «цвета нет».

    Иначе ре-фетч снесёт живой цвет при первом же 503.
    """
    spy = _Spy(None)

    with pytest.raises(RuntimeError):
        await spy.get_release_vinyl_color("123")


@pytest.mark.asyncio
async def test_partial_payload_never_reaches_the_release_cache(monkeypatch):
    """В ключе `release` лежит полный payload карточки.

    Подсунуть туда огрызок без цен и миниатюры — сломать карточку записи для
    всех остальных, поэтому узкий метод в кэш не пишет вообще.
    """
    import app.services.discogs as discogs_mod

    writes = []

    class _Cache:
        async def get(self, ns, key):
            return None

        async def set(self, ns, key, value, ttl=None):
            writes.append((ns, key))

        async def delete(self, ns, key):
            pass

        async def exists(self, ns, key):
            return False

    monkeypatch.setattr(discogs_mod, "cache", _Cache())
    spy = _Spy({"formats": [{"name": "Vinyl", "text": "Green"}]})

    await spy.get_release_vinyl_color("123")

    assert writes == []
