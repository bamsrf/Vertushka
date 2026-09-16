"""Политика кэширования обложек: годовой immutable вместо вечных перезагрузок.

Зачем файл. Владелец 16.09.2026: «обложки грузятся заново при каждом заходе».
Причин было две, и обе про кэш, а не про скорость сети:

  1. Витрина Маркета строила URL обложки в SQL и теряла метку версии `?v=`.
     Без метки nginx обязан отдавать Cache-Control всего на неделю — дольше
     нельзя, потому что файл по тому же пути перезаписывается апгрейдом
     качества. С меткой URL меняется вместе с содержимым, и можно честно
     сказать «immutable, год».
  2. Промах бакета не кэшировался вовсе: сорок плиток с отсутствующей
     обложкой будили FastAPI сорок раз подряд.
"""
import re
from pathlib import Path

from app.api import market

NGINX = (Path(__file__).resolve().parents[1] / "nginx" / "nginx.conf").read_text(encoding="utf-8")


def test_market_url_carries_version():
    """URL обложки в витрине несёт `?v=` из cover_cached_at."""
    assert "extract(epoch from r.cover_cached_at)" in market._COVER_BRIDGE
    assert "'?v='" in market._COVER_BRIDGE


def test_version_is_optional_not_broken():
    """Нет метки — нет и хвоста: COALESCE отдаёт пустую строку, а не 'None'.

    Иначе запись без cover_cached_at получила бы битый URL вида
    `/covers/123.jpg?v=` и вылетела бы из кэша навсегда.
    """
    assert "COALESCE('?v='" in market._COVER_BRIDGE


def test_nginx_gives_year_only_to_versioned_urls():
    """Годовой immutable — ТОЛЬКО для URL с меткой.

    Без метки год означал бы, что апгрейд качества никогда не доедет до
    установленных приложений.
    """
    m = re.search(r"map \$arg_v \$cover_cc \{(.+?)\}", NGINX, re.S)
    assert m, "map $arg_v не найден"
    body = m.group(1)
    assert "immutable" in body
    default_line = next(l for l in body.splitlines() if "default" in l)
    empty_line = next(l for l in body.splitlines() if '""' in l)
    assert "31536000" in default_line, "с меткой — год"
    assert "604800" in empty_line, "без метки — неделя"


def test_bucket_miss_is_negatively_cached():
    """404 от бакета кэшируется коротко, чтобы не будить FastAPI пачками."""
    assert NGINX.count("proxy_cache_valid 404 1m;") == 2, (
        "негативный кэш нужен в обоих server-блоках: api и web"
    )


def test_derivative_cache_has_room():
    """Кэш деривативов не должен быть меньше рабочего набора витрины."""
    m = re.search(r"proxy_cache_path /var/cache/nginx_covers .*?max_size=(\d+)g", NGINX)
    assert m and int(m.group(1)) >= 3
