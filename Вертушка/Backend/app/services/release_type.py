"""Единая классификация типа релиза (album / compilation / ep / single / other).

ЕДИНСТВЕННЫЙ источник правды. Три пути выдачи — локальный дамп-индекс
(`discogs_index.get_artist_masters_local`), live Discogs (`discogs.py`) и
фронтовый фолбэк — обязаны звать этот модуль, а не держать свои регексы.
Раньше правила были продублированы в SQL-агрегатах и в двух питоновых
функциях, расходились (напр. `umd` был в `_is_video`, но не в SQL-регексе) и
чинились точечно — отсюда «мешанина» в фильтре «Альбомы».

## Модель

Discogs `<descriptions>` смешивает три ортогональные вещи:

  * **тип релиза** — Album, Single, EP, Mini-Album, Maxi-Single, Compilation,
    Mixtape. Это единственное, что нас интересует;
  * **носитель/тираж** — LP, 12", 45 RPM, Reissue, Limited Edition, Stereo.
    Типа не несёт (кроме дюймовок, см. ниже);
  * **служебное** — Promo, Sampler, Advance, Transcription, Interview,
    Test Pressing, DVD-Video. Не релиз артиста, а промо-материал.

Отсюда три уровня: `TYPE_*` → служебное (`other`) → носитель (эвристика).

## Порядок разбора одной версии

Служебные маркеры проверяются ПЕРВЫМИ: `CD, Sampler, Promo` — это промо-диск,
даже если там же стоит Compilation. Затем типовые дескрипторы от узкого к
широкому: `Mini-Album` должен дать `ep`, а не `album` (подстрока «album» ловила
его и уводила радиохедовский «Airbag / How Am I Driving?» в альбомы).

## Голосование по группе

Тип мастера — плюрализм по РАЗЛИЧНЫМ форматам его версий; ничьи ломаются по
специфичности (single > ep > compilation > album). Булев `bool_or`, стоявший
здесь раньше, давал альбому приоритет над всем: у «My Iron Lung» (EP c LP-
изданием) один `Vinyl, LP` перебивал четыре EP-версии.

Служебные версии в голосовании не участвуют — но если ВСЕ версии служебные,
группа и есть промо-материал → `other`.
"""
from __future__ import annotations

import re

ALBUM = "album"
COMPILATION = "compilation"
EP = "ep"
SINGLE = "single"
OTHER = "other"

#: Порядок специфичности для tie-break: чем раньше, тем «уже» тип. EP выше
#: сингла: у «Queen's First E.P.» ровно по одному EP- и сингл-изданию, и EP
#: здесь — то, чем релиз назван.
_SPECIFICITY = (EP, SINGLE, COMPILATION, ALBUM)

#: Служебные носители и пометки — не релиз артиста. Видео-форматы здесь же:
#: DVD-концерты, промо-видеокассеты (U-matic/Betacam) и UMD текли в «Альбомы».
#: NB: голый "dvd" сюда НЕ входит — DVD-Audio музыкальный носитель; он ловится
#: слабым правилом _WEAK_VIDEO_RE уже после типовых дескрипторов.
#: NB: `Mixed` / `Partially Mixed` сюда НЕ входят — это способ подачи
#: (непрерывный микс), а не промо-материал. На дампе они демотировали 4k
#: легитимных микс-сборников и альбомы вроде `CD, Album, Partially Mixed`.
#: `Mixtape` — другое дело, отдельный дескриптор и правда не релиз артиста.
_SERVICE_RE = re.compile(
    r"transcription|interview|sampler|advance|test pressing|acetate|"
    r"\bpromo\b|mixtape|unofficial release|"
    r"cd-?rom|floppy|screen ?saver|"
    r"vhs|blu-?ray|laserdisc|\bumd\b|u-?matic|betacam|betamax|"
    r"video ?2000|video8|hi8|mini ?dv|\bvcd\b|\bsvcd\b|\bced\b|\bcdv\b|"
    r"dvd-?video",
    re.IGNORECASE,
)

#: Типовые дескрипторы Discogs, от узкого к широкому. Порядок значим.
#: `\bep\b` со словарной границей — иначе «ep» ловилось внутри слов.
#: `single` с отрицательным lookahead на «sided»: `Cassette, Single Sided` —
#: это односторонняя кассета (носитель), а не сингл (42k строк в дампе).
#: Голый `Mini` в EP-правило НЕ входит: это 3" CD (носитель), и по нему вся
#: сингловая дискография Queen — Bohemian Rhapsody, Under Pressure — числилась
#: как EP. `Mini-Album` — другое дело, он тип.
_TYPE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (SINGLE, re.compile(r"maxi-?single|\bsingle\b(?!\s*sided)", re.IGNORECASE)),
    (EP, re.compile(r"mini-?album|\bep\b", re.IGNORECASE)),
    (COMPILATION, re.compile(r"compilation", re.IGNORECASE)),
    (ALBUM, re.compile(r"\balbum\b|\blp\b", re.IGNORECASE)),
)

#: Носитель без типового дескриптора. 7"/шеллак/78 rpm — синглы по определению
#: эпохи; 12"/10" без Album/LP-пометки — макси и ремикс-катки.
_MEDIUM_RE = re.compile(r'7"|10"|12"|shellac|78 rpm', re.IGNORECASE)

#: Слабый видео-признак: голый dvd/video без «audio». Проверяется ПОСЛЕ типовых
#: дескрипторов, иначе `DVD, Album` (DVD-Audio издание альбома) уходило бы в
#: `other`. Явное видео (DVD-Video, VHS, UMD) сидит в _SERVICE_RE и перебивает
#: тип: `VHS, Compilation` — это видеокассета, а не сборник.
_WEAK_VIDEO_RE = re.compile(r"dvd|video", re.IGNORECASE)
_AUDIO_RE = re.compile(r"audio", re.IGNORECASE)


def classify_format(format_str: str | None) -> str | None:
    """Тип ОДНОЙ версии по строке формата (`"CD, Album"`, `"Vinyl, 12\""`).

    Возвращает `OTHER` для служебных носителей, один из типов — при явном
    дескрипторе или узнаваемом носителе, и `None` когда доказательств нет
    (`"CD"`, `"Cassette, Reissue"`, `"File, MP3"`). `None` — это «не знаю», и
    вызывающий обязан отличать его от `OTHER`: голосование по группе
    игнорирует `None`, но учитывает `OTHER`.
    """
    if not format_str or not format_str.strip():
        return None
    if _SERVICE_RE.search(format_str):
        return OTHER
    for release_type, pattern in _TYPE_RULES:
        if pattern.search(format_str):
            return release_type
    if _MEDIUM_RE.search(format_str):
        return SINGLE
    if _WEAK_VIDEO_RE.search(format_str) and not _AUDIO_RE.search(format_str):
        return OTHER
    return None


def classify_group(format_strs: "list[str | None]") -> str:
    """Тип мастер-группы по форматам ВСЕХ её версий.

    Плюрализм среди типизированных версий, ничья — по специфичности. Если
    типизированных нет: все версии цифровые (`File, …`) → `single` (цифра без
    Album-пометки почти всегда сингл), иначе → `other`.
    """
    votes: dict[str, int] = {}
    seen: set[str] = set()
    digital = bool(format_strs)
    for raw in format_strs:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        if not raw.lower().startswith("file"):
            digital = False
        release_type = classify_format(raw)
        if release_type is not None and release_type != OTHER:
            votes[release_type] = votes.get(release_type, 0) + 1
    if not seen:
        return OTHER
    if votes:
        top = max(votes.values())
        for candidate in _SPECIFICITY:
            if votes.get(candidate) == top:
                return candidate
    return SINGLE if digital else OTHER
