"""Словарь верхнеуровневых жанров Discogs и безопасный разбор склейки.

`records.genre` хранит жанры релиза склеенными через ", " — так их пишет и
живой путь (`DiscogsService.get_release`), и загрузчик из дампа
(`scripts/load_release_genres`). Разбирать эту склейку простым `split(",")`
нельзя: ровно одно имя словаря само содержит запятые — «Folk, World, &
Country». Наивный сплит превращает одну пластинку в три несуществующих жанра
(`folk`, `world`, `& country`) и, например, задирает ачивки «5 разных жанров» /
«10 разных жанров» втрое.

До бэкфилла жанров из дампа (25.08.2026) баг был незаметен: жанр стоял у ~390
записей из ~30 тысяч, и фолк среди них почти не попадался.
"""
from __future__ import annotations

import re

#: Верхний уровень Discogs целиком — закрытый список из 15 значений. Именно он
#: приезжает в `records.genre`; поджанры («Techno», «Indie Rock») живут в
#: `records.style` и сюда не попадают.
DISCOGS_GENRES: tuple[str, ...] = (
    "Blues",
    "Brass & Military",
    "Children's",
    "Classical",
    "Electronic",
    "Folk, World, & Country",
    "Funk / Soul",
    "Hip Hop",
    "Jazz",
    "Latin",
    "Non-Music",
    "Pop",
    "Reggae",
    "Rock",
    "Stage & Screen",
)

#: Имена словаря, внутри которых есть запятая — их надо вынуть до сплита.
_COMMA_GENRES: tuple[str, ...] = tuple(g for g in DISCOGS_GENRES if "," in g)
_COMMA_PATTERNS = [
    (re.compile(re.escape(g), re.IGNORECASE), f"\x00{i}\x00", g)
    for i, g in enumerate(_COMMA_GENRES)
]


def split_genres(value: str | None) -> list[str]:
    """«Electronic, Rock» → ["Electronic", "Rock"], сохраняя составные имена.

    «Folk, World, & Country, Rock» → ["Folk, World, & Country", "Rock"].
    Порядок сохраняется, пустые куски отбрасываются. Незнакомые значения
    (ручной ввод юзера в своей записи) проходят как есть — словарь тут фильтром
    не работает, только защищает известные составные имена.
    """
    if not value or not value.strip():
        return []
    tmp = value
    restore: dict[str, str] = {}
    for pattern, token, original in _COMMA_PATTERNS:
        tmp, found = pattern.subn(token, tmp)
        if found:
            restore[token] = original
    parts = (p.strip() for p in tmp.split(","))
    return [restore.get(p, p) for p in parts if p]
