"""Каждое имя иконки в Mobile обязано резолвиться в реестре <Icon>.

Icon.tsx на неизвестное имя молча отдаёт `plus` — экран не падает, просто
вместо флажка «Пожаловаться» рисуется плюс. Поймать это глазами почти
невозможно: иконка есть, она просто не та. Поэтому сверяем статикой —
собираем все литеральные имена из .tsx и требуем ключ в REGISTRY или в
таблице легаси-алиасов Ionicons.

Парсим регуляркой: тянуть node в pytest ради одного файла не хочется
(тот же приём, что в test_achievement_levels.py).
"""
import re
from pathlib import Path

import pytest

MOBILE = Path(__file__).resolve().parents[2] / "Mobile"
ICON_TSX = MOBILE / "components" / "ui" / "Icon.tsx"

pytestmark = pytest.mark.skipif(
    not ICON_TSX.exists(), reason="Mobile не в этом чекауте"
)


def _known_names() -> set[str]:
    """Ключи REGISTRY + IONICON_ALIASES: и то и другое — `'имя': значение`."""
    src = ICON_TSX.read_text(encoding="utf-8")
    return set(re.findall(r"^\s+'([a-z0-9.-]+)':\s*", src, re.M))


def _used_names() -> dict[str, set[str]]:
    """{имя иконки: {файлы, где встретилось}} по всем .tsx.

    Ловим два способа задать иконку: проп `<Icon name="…">` и поле
    `icon: '…'` в ActionSheet-экшенах. Динамические `name={cond ? a : b}`
    пропускаем — там литерала нет.
    """
    used: dict[str, set[str]] = {}
    for path in MOBILE.rglob("*.tsx"):
        if "node_modules" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        names = re.findall(r'<Icon\s[^>]*?name=["\']([a-z0-9-]+)["\']', text, re.S)
        names += re.findall(r"icon:\s*'([a-z0-9-]+)'", text)
        for name in names:
            used.setdefault(name, set()).add(str(path.relative_to(MOBILE)))
    return used


def test_every_icon_name_resolves():
    known = _known_names()
    unknown = {n: sorted(f) for n, f in _used_names().items() if n not in known}
    assert not unknown, (
        "имена иконок без записи в Icon.tsx — отрисуются как 'plus': "
        + "; ".join(f"{n} ({', '.join(files)})" for n, files in sorted(unknown.items()))
    )


def test_report_action_uses_flag():
    """Жалоба на чужую user-запись — флажок, а не что-то ещё."""
    known = _known_names()
    assert "flag-outline" in known
    assert "flag" in known

    record_screen = (MOBILE / "app" / "record" / "[id].tsx").read_text(encoding="utf-8")
    assert record_screen.count("flag-outline") == 2, (
        "флажок должен стоять и в шапке карточки, и в пункте «Пожаловаться»"
    )
