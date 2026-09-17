"""Выеденный бюджет Discogs не должен означать вечную заглушку.

17.09.2026, замер на проде: из 772 обложек витрины 6 отдавали 404. У всех был
живой `cover_image_url`, но запрос упирался в `_deny_discogs_by_budget` —
дневной лимит картинок Discogs исчерпан → жёсткий 404 → клиент остаётся с
заглушкой навсегда.

Обидное здесь в том, что CAA (офлайн-маппинг), Deezer, iTunes и Yandex
бюджета Discogs не тратят вовсе, лестница к ним давно написана, но вызывалась
только в ветке «у записи вообще нет URL». То есть мы отказывали ровно там, где
бесплатные каналы и нужны: бюджет выедается в час пик.

Сторожим три вещи: при отказе по бюджету лестница действительно запускается,
последняя (платная) ступень в ней выключена, и найденное отдаётся редиректом
плюс уходит в зеркалирование.
"""
import asyncio

import pytest

from app.api import covers as covers_api


class _Row(dict):
    """mappings()-строка индекса: и ключи, и атрибуты."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover — обращение к лишнему полю = баг
            raise AttributeError(name) from exc


def test_free_ladder_runs_without_the_paid_rung(monkeypatch):
    """allow_discogs=False обязан дойти до лестницы, иначе ступень Discogs
    отработает при выеденном бюджете — 403 через минуту вместо обложки."""
    seen = {}

    async def fake_guarded(db, discogs_id, row, allow_discogs=True):
        seen["id"] = discogs_id
        seen["allow_discogs"] = allow_discogs
        seen["row"] = dict(row)
        return "https://coverartarchive.org/release/x/front-1200.jpg"

    monkeypatch.setattr(covers_api, "_live_resolve_guarded", fake_guarded)

    out = asyncio.run(
        covers_api._free_sources_on_budget_denial(
            object(), "15506610",
            {"artist": "Lyle Lovett", "title": "Pontiac", "year": 1987, "barcode_norm": None},
        )
    )

    assert out == "https://coverartarchive.org/release/x/front-1200.jpg"
    assert seen["allow_discogs"] is False, "платная ступень обязана быть выключена"
    assert seen["id"] == "15506610"
    assert seen["row"]["artist"] == "Lyle Lovett"


def test_meta_is_optional_because_caa_works_by_id_alone(monkeypatch):
    """CAA ходит через mb_discogs_map по одному discogs_id. Требовать
    артиста с названием значило бы отказать записям, у которых их нет."""
    captured = {}

    async def fake_guarded(db, discogs_id, row, allow_discogs=True):
        captured["row"] = dict(row)
        return None

    monkeypatch.setattr(covers_api, "_live_resolve_guarded", fake_guarded)

    out = asyncio.run(covers_api._free_sources_on_budget_denial(object(), "123"))

    assert out is None
    # Ключи обязаны присутствовать: лестница читает их по индексу, не .get().
    assert set(captured["row"]) == {"artist", "title", "year", "barcode_norm"}
    assert all(v is None for v in captured["row"].values())


@pytest.mark.parametrize("found", [True, False])
def test_paid_rung_is_skipped_only_when_asked(monkeypatch, found):
    """Сама лестница: при allow_discogs=False ступень Discogs не вызывается,
    при True — вызывается (иначе мы молча оборвали бы обычный резолв)."""
    called = {"discogs": 0}

    class _FakeDiscogs:
        async def get_release_cover(self, discogs_id):
            called["discogs"] += 1
            return "https://i.discogs.com/paid.jpeg"

    import app.services.discogs as discogs_mod
    monkeypatch.setattr(discogs_mod, "DiscogsService", _FakeDiscogs)

    # Все бесплатные ступени пустые → доходим ровно до последней.
    import app.services.cover_fallback as cf
    import app.services.deezer as dz
    import app.services.yandex_music as ym

    async def _none(*a, **kw):
        return None

    monkeypatch.setattr(cf, "caa_cover_url_by_mbid", _none)
    monkeypatch.setattr(cf, "cover_url_by_artist_title", _none)
    monkeypatch.setattr(dz, "cover_by_meta", _none)
    monkeypatch.setattr(ym, "cover_by_meta", _none)

    out = asyncio.run(
        covers_api._resolve_cover_live(
            "999", "A", "T", 1990, None, allow_discogs=found
        )
    )

    if found:
        assert called["discogs"] == 1 and out == "https://i.discogs.com/paid.jpeg"
    else:
        assert called["discogs"] == 0 and out is None
