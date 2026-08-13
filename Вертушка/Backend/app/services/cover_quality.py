"""Определение «тира» обложки по URL — мастер или мелкий превью.

Зачем: поле `cover_image_url` исторически используется для двух разных целей —
как источник для показа и как источник для зеркалирования в мастер. Discogs
отдаёт в `/masters/{id}/versions` только `thumb` (150px, размер запечён в
подпись HMAC — его нельзя увеличить, подмена `w:` даёт 403). Раньше такой thumb
молча становился мастером: зеркало клало 150px на диск, imgproxy честно резал
из него, и деталь-экран получал апскейл ×8. Плюс персист thumb'а в
`discogs_releases_index.cover_image_url` закрывал строку для офлайн-канала CAA
(тот пишет только в `IS NULL`), то есть full-1200 больше никогда не приезжал.

Здесь — дешёвый пре-фильтр без сети. Авторитетная проверка всё равно по факту
декода (см. `cover_storage._encode_and_place`): формы URL у источников меняются,
а пиксели не врут. Поэтому неизвестный URL считается ДОПУСТИМЫМ — гейт не
должен рубить источник только потому, что мы не разобрали его схему.
"""
import re

# Порог «это мастер». Деталь-экран рендерит обложку почти во всю ширину
# (~390pt → 1170px на 3x), мастер капится 1000px. 500px — граница, ниже которой
# апскейл на детали видно глазом (замер из COVERS_ARCHITECTURE_NORMALIZATION).
MASTER_MIN_SIDE = 500

# imgproxy-стиль (Discogs i.discogs.com, наш /covers/w/): размеры сегментами пути.
_IMGPROXY_W = re.compile(r"(?:^|/)w:(\d+)(?:/|$)")
_IMGPROXY_H = re.compile(r"(?:^|/)h:(\d+)(?:/|$)")
# Наше зеркало: /covers/w/{px}/{name}.jpg
_MIRROR_W = re.compile(r"/covers/w/(\d+)/")
# Cover Art Archive: front-250 / front-500 / front-1200, либо {imageid}-250.jpg.
# Голый /front (без суффикса) — оригинал, размер неизвестен ⇒ не матчим.
_CAA_SIZE = re.compile(r"/(?:front|back|\d+)-(\d+)(?:\.\w+)?(?:\?|$)")
# iTunes / mzstatic: 100x100bb.jpg, 600x600bb.jpg
_ITUNES_SIZE = re.compile(r"/(\d+)x(\d+)[a-z]*\.\w+(?:\?|$)")
# Deezer: /images/cover/{md5}/{W}x{H}-...
_DEEZER_SIZE = re.compile(r"/images/[a-z]+/[0-9a-f]+/(\d+)x(\d+)")


def min_side_from_url(url: str | None) -> int | None:
    """Минимальная сторона картинки, если её видно из URL. Иначе None.

    None означает «не знаю», а НЕ «мелкая»: у CAA `/front` и у store-native
    ссылок размера в URL нет, и рубить их было бы регрессией покрытия.
    """
    if not url:
        return None

    sides: list[int] = []

    for rx in (_IMGPROXY_W, _IMGPROXY_H, _MIRROR_W, _CAA_SIZE):
        for m in rx.finditer(url):
            sides.append(int(m.group(1)))

    for rx in (_ITUNES_SIZE, _DEEZER_SIZE):
        for m in rx.finditer(url):
            sides.extend((int(m.group(1)), int(m.group(2))))

    # Отсекаем мусорные нули (например w:0 — «сторона по пропорции»).
    sides = [s for s in sides if s > 0]
    return min(sides) if sides else None


def is_thumb_grade(url: str | None) -> bool:
    """True — URL заведомо мельче мастера, зеркалировать/персистить нельзя.

    Неизвестный размер → False (пропускаем, решит проверка по декоду).
    """
    side = min_side_from_url(url)
    return side is not None and side < MASTER_MIN_SIDE


def is_master_grade(url: str | None) -> bool:
    """True — URL пригоден как источник мастера (известно крупный или неизвестный).

    Пустой URL мастером не является.
    """
    return bool(url) and not is_thumb_grade(url)
