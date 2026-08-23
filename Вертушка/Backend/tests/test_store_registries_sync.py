"""Четыре реестра магазинов обязаны сходиться по слагам.

  1. Реестр парсеров — `@register_parser(...)` в app/services/scrapers/shops/*;
  2. STORES в app/scripts/seed_stores.py — что сеем в таблицу `stores`;
  3. STORE_REGISTRY в Mobile/components/market/StoreLogo.tsx — имя/лого в приложении;
  4. _LOCAL_STORE_LOGOS в app/web/routes.py — белый список логотипов на вебе.

Они расходятся молча: магазин, заведённый в прод-БД руками мимо сидинга,
не существует для seed_stores (регресс 2026-08-23: skifmusic и rotaryrecords
жили только на проде, а vinyl_ru в скрипте остался активным — полный прогон
сидинга реанимировал бы выключенный магазин). Слаг без парсера падает только
ночью в шедулере; слаг без записи в мобилке рисуется безликой монограммой.

Правило: каждый посеянный магазин обязан иметь парсер, запись в STORE_REGISTRY
и логотип в вебе — и наоборот, в реестрах не должно быть «ничьих» слагов.
Допустимые исключения оформляются явными множествами ниже, с комментарием
почему (сейчас исключений нет).

Смежный test_store_logos.py сверяет _LOCAL_STORE_LOGOS с PNG-файлами двух
директорий — здесь его не дублируем, сверяем только слаги между реестрами.
Парсим .tsx регуляркой — приём из test_mobile_icon_registry.py.
"""
import re
from pathlib import Path

import pytest

import app.services.scrapers.shops  # noqa: F401 — импорт наполняет реестр парсеров
from app.scripts.seed_stores import STORES
from app.services.scrapers.registry import all_parsers
from app.web.routes import _LOCAL_STORE_LOGOS

_STORE_LOGO_TSX = (
    Path(__file__).resolve().parents[2]
    / "Mobile" / "components" / "market" / "StoreLogo.tsx"
)

# ---- Допустимые исключения (каждое — с причиной) ----------------------- #
# Парсер есть, но магазин сознательно не сеем (нет таких).
PARSER_WITHOUT_SEED: set[str] = set()
# Посеян, но парсера нет — например, магазин с ручным импортом (нет таких).
SEED_WITHOUT_PARSER: set[str] = set()
# Посеян, но без логотипа в мобилке/вебе — рисуется монограмма (нет таких).
SEED_WITHOUT_LOGO: set[str] = set()


def _seed_slugs() -> set[str]:
    return {s["slug"] for s in STORES}


def _mobile_registry_slugs() -> set[str]:
    """Ключи верхнего уровня STORE_REGISTRY из StoreLogo.tsx.

    Ключ — идентификатор с двумя пробелами отступа и `{` после двоеточия;
    вложенные поля (name/monogram/bgColor/logoSource) под это не подходят.
    """
    src = _STORE_LOGO_TSX.read_text(encoding="utf-8")
    match = re.search(r"const STORE_REGISTRY[^=]*=\s*\{(.*?)\n\};", src, re.S)
    assert match, "STORE_REGISTRY не найден в StoreLogo.tsx — тест надо обновить"
    return set(re.findall(r"^  ([a-z0-9_]+):\s*\{", match.group(1), re.M))


def test_seed_matches_parser_registry():
    """Каждый посеянный магазин имеет парсер, каждый парсер — посев."""
    seeded, parsers = _seed_slugs(), set(all_parsers())

    no_parser = seeded - parsers - SEED_WITHOUT_PARSER
    assert not no_parser, (
        f"в STORES есть магазины без парсера: {sorted(no_parser)} — "
        "ночной crawl упадёт на get_parser()"
    )

    no_seed = parsers - seeded - PARSER_WITHOUT_SEED
    assert not no_seed, (
        f"парсер зарегистрирован, а в STORES магазина нет: {sorted(no_seed)} — "
        "магазин существует только в прод-БД, полный прогон сидинга о нём не знает"
    )


def test_parser_class_values_registered():
    """`parser_class` в посеве — это slug из @register_parser, не имя класса."""
    parsers = set(all_parsers())
    bad = {s["slug"]: s["parser_class"] for s in STORES
           if s["parser_class"] not in parsers}
    assert not bad, f"parser_class не найден в реестре парсеров: {bad}"


@pytest.mark.skipif(not _STORE_LOGO_TSX.exists(), reason="Mobile не в этом чекауте")
def test_seed_matches_mobile_store_registry():
    """Каждый посеянный магазин имеет запись в STORE_REGISTRY мобилки — и наоборот."""
    seeded, mobile = _seed_slugs(), _mobile_registry_slugs()

    no_entry = seeded - mobile - SEED_WITHOUT_LOGO
    assert not no_entry, (
        f"магазины без записи в STORE_REGISTRY (StoreLogo.tsx): {sorted(no_entry)} — "
        "в приложении вместо логотипа будет монограмма «?»"
    )

    orphan = mobile - seeded
    assert not orphan, (
        f"в STORE_REGISTRY есть слаги, которых нет в STORES: {sorted(orphan)} — "
        "либо магазин забыли посеять, либо запись в мобилке мёртвая"
    )


def test_seed_matches_web_logo_whitelist():
    """Каждый посеянный магазин — в _LOCAL_STORE_LOGOS веба, и наоборот."""
    seeded = _seed_slugs()

    no_logo = seeded - _LOCAL_STORE_LOGOS - SEED_WITHOUT_LOGO
    assert not no_logo, (
        f"магазины без слага в _LOCAL_STORE_LOGOS (web/routes.py): {sorted(no_logo)} — "
        "публичные страницы нарисуют монограмму при живом PNG"
    )

    orphan = _LOCAL_STORE_LOGOS - seeded
    assert not orphan, (
        f"в _LOCAL_STORE_LOGOS есть слаги, которых нет в STORES: {sorted(orphan)} — "
        "либо магазин забыли посеять, либо слаг в белом списке мёртвый"
    )


def test_vinyl_ru_stays_inactive_in_seed():
    """Регресс 2026-08-23: vinyl_ru выключен на проде с 09.08 (36-часовой
    обход), а в сидинге стоял is_active=True — полный прогон скрипта молча
    реанимировал бы магазин. Включать обратно только после перевода на
    YML/инкремент (MARKET_STORES_SCALING.md §7a) — тогда и снять этот тест.
    """
    vinyl_ru = next(s for s in STORES if s["slug"] == "vinyl_ru")
    assert vinyl_ru["is_active"] is False
