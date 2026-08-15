"""Бесконечные анимации на публичных страницах должны быть композитными.

Инцидент 2026-08-15: на десктопе обложки мерцали при скролле. Виноваты были не
картинки, а три вечных анимации, которые дёргали свойства раскладки и покраски:

  • .cta::after   — анимировал `left` (раскладка!), и жил в position:fixed
                    поверх скроллящейся страницы, то есть молотил постоянно;
  • .reserved-badge — анимировал box-shadow (покраска) на каждом бейдже;
  • .topbar.stuck — backdrop-filter заставлял пересобирать картинку под полосой
                    на каждом кадре скролла.

Браузер умеет крутить на GPU только transform и opacity. Всё остальное в
`infinite`-анимации — это перерисовка каждый кадр, и на странице с сотней
изображений она конкурирует с их декодированием.
"""
import re
from pathlib import Path

import pytest

TEMPLATES = Path("app/web/templates")
PAGES = ["public_profile.html", "support.html", "_support.html", "_support_teaser.html"]

# Что дёшево анимировать бесконечно. transform/opacity композитны; visibility и
# animation-timing-function не создают работы сами по себе.
COMPOSITE_SAFE = {"transform", "opacity", "visibility", "animation-timing-function"}


def read(name: str) -> str:
    """CSS без комментариев: слово из пояснения — не объявление."""
    raw = (TEMPLATES / name).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", "", raw, flags=re.S)


def infinite_animation_names(css: str) -> set[str]:
    """Имена анимаций, объявленных как infinite."""
    names = set()
    for decl in re.findall(r"animation:\s*([^;]+);", css):
        if "infinite" not in decl:
            continue
        # первый токен, который не длительность/easing/ключевое слово
        for token in decl.split():
            if re.match(r"^[a-zA-Z][\w-]*$", token) and token not in {
                "infinite", "linear", "ease", "ease-in", "ease-out",
                "ease-in-out", "alternate", "both", "forwards", "backwards",
                "normal", "reverse", "running", "paused", "none",
            } and not token.startswith("cubic-bezier"):
                names.add(token)
                break
    return names


def keyframe_properties(css: str, name: str) -> set[str]:
    m = re.search(r"@keyframes\s+" + re.escape(name) + r"\s*\{", css)
    if not m:
        return set()
    i = m.end()
    depth, body = 1, []
    while i < len(css) and depth:
        ch = css[i]
        depth += ch == "{"
        depth -= ch == "}"
        if depth:
            body.append(ch)
        i += 1
    return {p.strip() for p in re.findall(r"([a-z-]+)\s*:", "".join(body))}


@pytest.mark.parametrize("page", PAGES)
def test_infinite_animations_touch_only_composite_properties(page):
    css = read(page)
    offenders = {}
    for name in infinite_animation_names(css):
        props = keyframe_properties(css, name)
        bad = props - COMPOSITE_SAFE
        if bad:
            offenders[name] = sorted(bad)
    assert not offenders, (
        f"{page}: бесконечные анимации дёргают некомпозитные свойства {offenders}. "
        "Каждый кадр — перерисовка; на странице с сотней обложек это мерцание "
        "при скролле. Переводить на transform/opacity."
    )


def test_sticky_header_has_no_backdrop_filter():
    """Блюр липкой полосы = пересборка картинки под ней на каждом кадре."""
    css = read("public_profile.html")
    m = re.search(r"\.topbar\.stuck\s*\{([^}]*)\}", css)
    assert m, "правило .topbar.stuck пропало"
    assert "backdrop-filter" not in m.group(1)


def test_rails_are_larger_on_desktop():
    """Подписи в каруселях набраны под телефон; на десктопе их поднимаем."""
    css = read("public_profile.html")
    desktop = re.findall(r"@media \(min-width: 721px\)\s*\{(.+?)\n        \}", css, re.S)
    joined = "\n".join(desktop)
    assert ".rail-meta-title" in joined and ".rail-meta-artist" in joined


def test_booking_explainer_is_larger_on_desktop():
    """«Как работает бронирование» на десктопе растянут на две колонки во всю
    ширину контента, а кегль остался телефонным (12.5px) — строки длинные и
    мелкие одновременно, читать неприятно."""
    css = read("public_profile.html")
    desktop = "\n".join(
        re.findall(r"@media \(min-width: 721px\)\s*\{(.+?)\n        \}", css, re.S)
    )
    m = re.search(r"\.booking-explainer \.step\s*\{[^}]*font-size:\s*([\d.]+)px", desktop)
    assert m, "на десктопе кегль блока бронирования не поднят"
    assert float(m.group(1)) >= 14, "меньше 14px на большом экране — всё ещё петит"


def test_rails_stop_while_page_scrolls():
    """Карусель не должна ехать, пока страница едет вертикально.

    На .rail висит mask-image, внутри — два десятка обложек, и трек двигается
    каждый кадр. Вместе с вертикальным скроллом это перерисовка маскированной
    полосы поверх декодирования картинок в сетке; именно в этот момент обложки
    и моргали.
    """
    js = read("public_profile.html")
    assert "is-scrolling" in js, "нет флага активного скролла"
    assert re.search(
        r"if \(visible && !paused && !pageScrolling\)", js
    ), "tick рейла не проверяет вертикальный скролл страницы"


def test_desktop_rail_area_fits_larger_type():
    """.rail-slot внутри .rail-area — absolute, контент не раздвигает контейнер.

    Замер на живой странице при 1000px: самая высокая карусель (в маркете есть
    ещё строка с ценой) заканчивается на 229px. С прежними 198px увеличенный
    кегль срезало по нижней кромке.
    """
    css = read("public_profile.html")
    # таких блоков на странице несколько — правило может быть в любом
    desktop = "\n".join(re.findall(r"@media \(min-width: 721px\)\s*\{(.+?)\n        \}", css, re.S))
    m = re.search(r"\.rail-area\s*\{[^}]*min-height:\s*(\d+)px", desktop)
    assert m, "на десктопе не задана высота .rail-area под новый кегль"
    assert int(m.group(1)) >= 232, "высоты не хватит самой длинной карточке (229px)"
