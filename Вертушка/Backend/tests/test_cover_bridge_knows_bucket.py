"""Мост обложки обязан знать про вечный слой.

Зачем файл. До S3 «зеркало есть» = «файл на диске», и условие моста смотрело
на cover_local_path. С включённым бакетом (28.08.2026) LRU стирает указатель,
оставляя cover_cached_at: файл жив, просто лежит в S3. Условие об этом не
знало — у выселенной записи без внешнего URL мост схлопывался в NULL, и
COALESCE подставлял фото с САЙТА МАГАЗИНА.

Итог на проде 16.09.2026: витрина «Скифмьюзика» отдавала 5 842 из 14 677
плиток (40%) ссылками на skifmusic.ru. Наша копия при этом лежала в бакете и
отдавалась за 15 КБ и 0.1 с, а магазинные ссылки с телефона владельца не
грузились по десять минут.

Это регрессия перехода на S3: LRU и мост разошлись в понимании того, что
считается зеркалом.
"""
from app.api import market


def test_bridge_fires_on_bucket_only_record():
    """cover_cached_at достаточно, даже когда local и url пустые."""
    assert "r.cover_cached_at IS NOT NULL" in market._COVER_BRIDGE


def test_bridge_still_requires_discogs_id():
    """Мост /covers/{id}.jpg адресуется discogs_id — без него он бессмыслен."""
    assert "r.discogs_id IS NOT NULL" in market._COVER_BRIDGE


def test_listing_expression_prefers_bridge_over_store_photo():
    """Порядок COALESCE: сначала наша копия, потом чужой сайт.

    Магазин — источник последней очереди: его хотлинк протухает, отдаётся
    медленно и не под нашим контролем.
    """
    expr = market._COVER_EXPR_LISTING
    assert expr.index("CASE") < expr.index("raw_payload")


def test_filters_count_bucket_as_a_cover():
    """Фильтр «есть хоть какая-то обложка» тоже обязан видеть бакет.

    Иначе запись с копией в вечном слое, но без диска и URL, просто выпадала
    бы из выдачи Маркета — то есть пластинка исчезала с витрины.
    """
    import inspect

    source = inspect.getsource(market)
    stale = source.count(
        "COALESCE(r.cover_local_path, r.cover_image_url, sl.raw_payload"
    )
    assert stale == 0, "остался фильтр, не знающий про cover_cached_at"


def test_cache_namespaces_bumped():
    """Версии кэша подняты вместе с формой ответа.

    Ответы Маркета лежат в Redis с уже готовыми URL: без бампа витрина ещё
    5–30 минут отдавала бы старые ссылки на магазины.

    Проверяем НИЖНЮЮ границу, а не точное число: версии бампаются при каждом
    изменении формы ответа, и жёсткая привязка ломала бы этот тест на каждой
    следующей правке — так и случилось сразу же, в PR про кэш обложек.
    Смысл теста — «не ниже той версии, на которой мост узнал про бакет».
    """
    import re

    def version(ns: str) -> int:
        m = re.search(r":v(\d+)$", ns)
        assert m, f"namespace без версии: {ns}"
        return int(m.group(1))

    assert version(market.CACHE_NS_SEARCH) >= 14
    assert version(market.CACHE_NS_STORE_LISTINGS) >= 5
    assert version(market.CACHE_NS_STORES) >= 4
