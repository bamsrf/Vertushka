"""Совместимость носителей для «другой версии» (alt-version).

Радар, пуши и секция «Другая версия мастера» подбирают альтернативу по
`discogs_master_id`. Мастер на Discogs объединяет ВСЕ издания альбома: винил,
CD, кассету и цифру (`File, MP3`). Без фильтра человеку, который ждёт винил,
радар предлагал mp3-файл за 29 990 ₽ — формально «другой прессинг того же
мастера», по сути мусор.

Правило: альтернатива показывается, только если носитель совпадает с
желаемым. Носитель определяем по `format_type` + `format_description` записи,
с запасным вариантом на `StoreListing.format_raw` (у store-native записей
форматов Discogs может не быть).

Строгость намеренная: если носитель альтернативы определить не удалось, а
желаемый известен — не предлагаем. Лучше не показать сомнительный аналог, чем
показать цифру вместо винила.
"""
from __future__ import annotations

import re

from app.services.achievements.media_format import (
    CASSETTE,
    CD,
    VINYL,
    parse_media,
)

#: Цифровой релиз: `File, MP3`, `File, FLAC, Album`, `Digital`.
DIGITAL = "digital"

#: Физические носители, по которым сверяем «то же самое или нет».
PHYSICAL = frozenset({VINYL, CD, CASSETTE})

_DIGITAL_RE = re.compile(
    r"\bfile\b|\bmp3\b|\bflac\b|\bwav\b|\baac\b|\balac\b|\baiff?\b|\bogg\b"
    r"|\bwma\b|\bdsd\b|\bdsf\b|digital|цифров",
    re.IGNORECASE,
)


def media_families(
    format_type: str | None,
    format_description: str | None = None,
) -> frozenset[str]:
    """Семейства носителя записи: `vinyl`/`cd`/`cassette`/`digital`.

    Пустое множество — носитель неизвестен. Гибриды («Vinyl, LP + File»)
    отдают оба семейства: винил-издание с кодом на скачивание остаётся винилом.
    """
    families = set(parse_media(format_type, format_description).families) & PHYSICAL
    blob = " ".join(p for p in (format_type, format_description) if p)
    if _DIGITAL_RE.search(blob):
        families.add(DIGITAL)
    return frozenset(families)


def is_compatible_alt(
    wanted: frozenset[str],
    alt: frozenset[str],
) -> bool:
    """Годится ли альтернатива с носителем `alt` тому, кто хочет `wanted`."""
    wanted_physical = wanted & PHYSICAL
    alt_physical = alt & PHYSICAL

    if wanted_physical:
        # Винил ищем винилом. Цифра и неопознанный носитель — мимо.
        return bool(wanted_physical & alt_physical)

    # Желаемый носитель неизвестен: отсекаем только заведомую цифру.
    return not (DIGITAL in alt and not alt_physical)


def alt_media_ok(
    wanted_format_type: str | None,
    wanted_format_description: str | None,
    alt_format_type: str | None,
    alt_format_description: str | None = None,
    alt_format_raw: str | None = None,
) -> bool:
    """Удобная обёртка: сверяет носители по «сырым» полям записей.

    `alt_format_raw` — `StoreListing.format_raw`, запасной источник, когда у
    записи-альтернативы полей Discogs нет.
    """
    alt = media_families(alt_format_type, alt_format_description)
    if not alt and alt_format_raw:
        alt = media_families(alt_format_raw)
    return is_compatible_alt(
        media_families(wanted_format_type, wanted_format_description),
        alt,
    )
