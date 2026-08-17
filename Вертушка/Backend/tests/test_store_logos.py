"""Логотипы магазинов лежат в трёх местах, и они обязаны совпадать.

  1. `Mobile/assets/store-logos/<slug>.png` — бандл приложения;
  2. `Backend/app/web/static/store-logos/<slug>.png` — публичные веб-страницы;
  3. `_LOCAL_STORE_LOGOS` в `app/web/routes.py` — белый список для (2).

Список и папка расходятся молча: положил файл, забыл slug — веб рисует
монограмму при живом PNG; добавил slug без файла — отдаёт 404 вместо картинки.
Ни то, ни другое не роняет тесты и не пишет в лог, поэтому проверяем здесь.
"""
from pathlib import Path

import pytest

from app.web.routes import _LOCAL_STORE_LOGOS

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_WEB_LOGOS = _BACKEND_ROOT / "app" / "web" / "static" / "store-logos"
_MOBILE_LOGOS = _BACKEND_ROOT.parent / "Mobile" / "assets" / "store-logos"


def _slugs(directory: Path) -> set[str]:
    return {p.stem for p in directory.glob("*.png")}


def test_every_whitelisted_slug_has_a_web_file():
    missing = sorted(_LOCAL_STORE_LOGOS - _slugs(_WEB_LOGOS))
    assert not missing, (
        f"в _LOCAL_STORE_LOGOS есть slug без PNG в {_WEB_LOGOS.name}/: {missing} — "
        "веб отдаст 404 вместо логотипа"
    )


def test_every_web_file_is_whitelisted():
    extra = sorted(_slugs(_WEB_LOGOS) - _LOCAL_STORE_LOGOS)
    assert not extra, (
        f"PNG есть, а slug в _LOCAL_STORE_LOGOS нет: {extra} — "
        "веб нарисует монограмму при живой картинке"
    )


@pytest.mark.skipif(not _MOBILE_LOGOS.is_dir(), reason="Mobile/ рядом нет (CI только для Backend)")
def test_web_and_mobile_logo_sets_match():
    """Один магазин — один логотип во всех витринах.

    Расхождение означает, что в приложении и на публичной странице у магазина
    разные лица (или на одной из них монограмма).
    """
    assert _slugs(_WEB_LOGOS) == _slugs(_MOBILE_LOGOS)


def test_long_play_logo_present():
    """Регрессия 2026-08-17: магазин подключили, логотип завезли отдельно."""
    assert "long_play" in _LOCAL_STORE_LOGOS
    assert (_WEB_LOGOS / "long_play.png").is_file()
