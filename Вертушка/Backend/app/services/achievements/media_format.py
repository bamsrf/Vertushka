"""Определение носителя пластинки для форматных серий ачивок.

Задача узкая: свести `Record.format_type` + `Record.format_description` к
семейству носителя — винил, кассета, CD, бокс-сет. Это НЕ то же, что
`services/release_type.py`: тот отвечает на вопрос «альбом или сингл»,
а здесь — «на чём издано».

Грабли, из-за которых нельзя смотреть только на `format_type`:

- **Бокс-сет почти никогда не лежит в `format_type`.** Discogs оставляет там
  `Vinyl` или `CD`, а `Box Set` кладёт дескриптором в `format_description`.
  Ловим по описанию.
- **Бокс — не отдельный носитель, а упаковка.** Бокс из четырёх винилов
  одновременно и винил, и бокс, поэтому семейства возвращаются множеством,
  а не одним значением.
- **CDr / HDCD / SACD — это CD.** Сворачиваем в одну семью, иначе «25 CD»
  недосчитывается у тех, кто собирает переиздания.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

VINYL = "vinyl"
CASSETTE = "cassette"
CD = "cd"
BOX_SET = "box_set"

#: Все семейства, которые считают форматные серии.
FAMILIES = (VINYL, CASSETTE, CD, BOX_SET)

_VINYL_RE = re.compile(r"\bvinyl\b|\blp\b|shellac|винил", re.IGNORECASE)
_CASSETTE_RE = re.compile(r"cassette|\bcass\b|microcassette|кассет", re.IGNORECASE)
# CDr/HDCD/SACD — семья CD. `CD-Video` исключаем: это видео, а не альбом.
_CD_RE = re.compile(r"\bcd\b|\bcdr\b|hdcd|sacd|компакт", re.IGNORECASE)
_CD_VIDEO_RE = re.compile(r"cd-?video|vcd", re.IGNORECASE)
_BOX_RE = re.compile(r"box\s*-?\s*set|бокс-?сет|боксет", re.IGNORECASE)

#: «10×Vinyl», «3 x CD» — количество дисков внутри издания.
_QTY_RE = re.compile(r"(\d+)\s*[x×]\s*", re.IGNORECASE)

#: Type IV / Metal — кассетная плёнка высшего класса.
_TYPE_IV_RE = re.compile(r"type\s*iv|\bmetal\b", re.IGNORECASE)

#: Лимитированность бокса.
_LIMITED_RE = re.compile(
    r"limited|numbered|anniversary|deluxe|лимит|нумерован|юбилей", re.IGNORECASE
)


@dataclass(frozen=True)
class MediaInfo:
    """Разбор носителя одной записи."""

    families: frozenset[str]
    #: Сколько физических носителей внутри издания (из «10×Vinyl»). 1 если не указано.
    qty: int
    is_type_iv: bool
    is_limited: bool

    def has(self, family: str) -> bool:
        return family in self.families


def _text(*parts: str | None) -> str:
    return " ".join(p for p in parts if p)


def parse_media(
    format_type: str | None,
    format_description: str | None = None,
) -> MediaInfo:
    """Разбирает поля формата записи в семейства носителя и попутные признаки."""
    blob = _text(format_type, format_description)
    families: set[str] = set()

    if _VINYL_RE.search(blob):
        families.add(VINYL)
    if _CASSETTE_RE.search(blob):
        families.add(CASSETTE)
    if _CD_RE.search(blob) and not _CD_VIDEO_RE.search(blob):
        families.add(CD)
    if _BOX_RE.search(blob):
        families.add(BOX_SET)

    qty_match = _QTY_RE.search(blob)
    qty = int(qty_match.group(1)) if qty_match else 1
    # Защита от мусорных значений вроде «100×File».
    if qty < 1 or qty > 200:
        qty = 1

    return MediaInfo(
        families=frozenset(families),
        qty=qty,
        is_type_iv=bool(_TYPE_IV_RE.search(blob)) and CASSETTE in families,
        is_limited=bool(_LIMITED_RE.search(blob)),
    )
