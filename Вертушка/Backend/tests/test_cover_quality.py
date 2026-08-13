"""Тир обложки по URL: мастер против мелкого превью.

Регрессия, которую сторожит файл: `/masters/{id}/versions` у Discogs отдаёт
только `thumb` (h:150/w:150, размер внутри подписи HMAC). Такой URL три недели
молча становился мастером — зеркало клало 150px на диск, imgproxy резал из
него, деталь-экран получал апскейл ×8. Отдельно: персист thumb'а в
`discogs_releases_index.cover_image_url` навсегда закрывал строку для
офлайн-канала CAA (тот пишет только в `IS NULL`).

Ключевое требование к гейту — асимметрия: заведомо мелкое рубим, неизвестное
пропускаем. Иначе первый же источник с неразобранной схемой URL (store-native,
голый CAA `/front`) потерял бы покрытие.
"""
import pytest

from app.services.cover_quality import (
    MASTER_MIN_SIDE,
    is_master_grade,
    is_thumb_grade,
    min_side_from_url,
)

# Живые формы URL. Discogs-примеры — из JS-бандла их же Android-приложения
# (3.0.21), где обе рецептуры лежат литералами: q:90/h:600/w:600 — основной тир,
# q:40/h:300/w:400 — дешёвый плейсхолдер.
_DISCOGS_600 = (
    "https://i.discogs.com/nJO1g8QP55xQshzotNRWogaADI8z_t5xskXbr7a1J1E"
    "/rs:fit/g:sm/q:90/h:600/w:600/czM6Ly9kaXNjb2dz.jpeg"
)
_DISCOGS_THUMB_150 = (
    "https://i.discogs.com/abc123/rs:fit/g:sm/q:40/h:150/w:150/czM6Ly9kaXNjb2dz.jpeg"
)
_DISCOGS_PLACEHOLDER_400x300 = (
    "https://i.discogs.com/abc123/rs:fit/g:sm/q:40/h:300/w:400/czM6Ly9kaXNjb2dz.jpeg"
)
_CAA_1200 = "https://coverartarchive.org/release/99b09d02-9cc9-3fed-8431-f162165a9371/front-1200"
_CAA_250 = "https://coverartarchive.org/release/99b09d02-9cc9-3fed-8431-f162165a9371/front-250"
_CAA_ORIGINAL = "https://coverartarchive.org/release/99b09d02-9cc9-3fed-8431-f162165a9371/front"
_ITUNES_600 = "https://is1-ssl.mzstatic.com/image/thumb/Music/x/y/z/600x600bb.jpg"
_ITUNES_100 = "https://is1-ssl.mzstatic.com/image/thumb/Music/x/y/z/100x100bb.jpg"
_DEEZER_XL = "https://e-cdns-images.dzcdn.net/images/cover/abc123def456/1000x1000-000000-80-0-0.jpg"
_DEEZER_MEDIUM = "https://e-cdns-images.dzcdn.net/images/cover/abc123def456/250x250-000000-80-0-0.jpg"
_OUR_MIRROR_MASTER = "https://api.vinyl-vertushka.ru/covers/736788.jpg"
_OUR_MIRROR_SIZED = "https://api.vinyl-vertushka.ru/covers/w/590/736788.jpg"
_STORE_NATIVE = "https://shop.example.ru/upload/iblock/1a2/cover.jpg"


@pytest.mark.parametrize(
    "url, expected",
    [
        (_DISCOGS_600, 600),
        (_DISCOGS_THUMB_150, 150),
        # min(400, 300) — берём меньшую сторону, иначе 400 прошло бы порог 500
        # только по одной оси и обложка всё равно пикселила бы по высоте.
        (_DISCOGS_PLACEHOLDER_400x300, 300),
        (_CAA_1200, 1200),
        (_CAA_250, 250),
        (_ITUNES_600, 600),
        (_ITUNES_100, 100),
        (_DEEZER_XL, 1000),
        (_DEEZER_MEDIUM, 250),
        (_OUR_MIRROR_SIZED, 590),
    ],
)
def test_min_side_parsed_from_known_schemes(url, expected):
    assert min_side_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        _CAA_ORIGINAL,      # голый /front — оригинал, размера в URL нет
        _OUR_MIRROR_MASTER,  # наш мастер — размер не в URL, он в файле
        _STORE_NATIVE,       # магазинный CDN — схема произвольная
    ],
)
def test_unknown_size_returns_none(url):
    assert min_side_from_url(url) is None


@pytest.mark.parametrize(
    "url",
    [_DISCOGS_THUMB_150, _DISCOGS_PLACEHOLDER_400x300, _CAA_250, _ITUNES_100, _DEEZER_MEDIUM],
)
def test_thumb_grade_rejected(url):
    assert is_thumb_grade(url) is True
    assert is_master_grade(url) is False


@pytest.mark.parametrize("url", [_DISCOGS_600, _CAA_1200, _ITUNES_600, _DEEZER_XL])
def test_master_grade_accepted(url):
    assert is_thumb_grade(url) is False
    assert is_master_grade(url) is True


@pytest.mark.parametrize("url", [_CAA_ORIGINAL, _OUR_MIRROR_MASTER, _STORE_NATIVE])
def test_unknown_size_is_not_blocked(url):
    """Асимметрия гейта: не знаем размер — пропускаем, решит проверка по декоду.

    Обратное поведение (рубить неизвестное) обрушило бы покрытие: у CAA
    `/front` и у store-native ссылок размера в URL нет в принципе.
    """
    assert is_thumb_grade(url) is False
    assert is_master_grade(url) is True


def test_empty_url_is_never_master():
    assert is_master_grade(None) is False
    assert is_master_grade("") is False


def test_threshold_boundary_is_inclusive_for_master():
    """Ровно MASTER_MIN_SIDE — уже мастер, ниже — нет."""
    at = f"https://i.discogs.com/x/rs:fit/w:{MASTER_MIN_SIDE}/h:{MASTER_MIN_SIDE}/y.jpeg"
    below = f"https://i.discogs.com/x/rs:fit/w:{MASTER_MIN_SIDE - 1}/h:{MASTER_MIN_SIDE - 1}/y.jpeg"
    assert is_thumb_grade(at) is False
    assert is_thumb_grade(below) is True


def test_zero_side_is_ignored_not_treated_as_tiny():
    """`w:0` у imgproxy = «сторона по пропорции», а не нулевая картинка.

    Наш собственный rewrite в nginx строит именно `rs:fit:{w}:0:0`, поэтому
    трактовать 0 как размер значило бы рубить свои же ссылки.
    """
    url = "https://i.discogs.com/x/rs:fit/w:800/h:0/y.jpeg"
    assert min_side_from_url(url) == 800
    assert is_thumb_grade(url) is False
