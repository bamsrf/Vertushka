"""Ночная очистка не имеет права съедать чужую коллекцию.

Инцидент 18.08.2026. В коллекции из 172 позиций 63 (37%) показывались размытым
blurhash-плейсхолдером вместо обложки. Blurhash считается ТОЛЬКО с уже лежащего
на диске файла — значит обложка была скачана и затем удалена.

Удалила её `cleanup_lru`, и сделала это по неверному допущению, записанному
прямо в коде: «discogs/store обложки эвиктить можно — само-лечатся из
cover_image_url при next view». Для Discogs это неверно: их ссылки подписаны и
протухают, поэтому self-heal получает 403, и плитка остаётся пустой НАВСЕГДА.
У всех 63 пострадавших cover_image_url вёл на discogs.com.

Усугубляло то, что цель очистки была недостижима (лимит 500 МБ при 3 ГБ на
диске, дотянуться она могла до 6% файлов) — то есть каждую ночь она сносила
всё, до чего дотягивалась.

Правило теперь: выселяем только то, что честно вернётся само.
"""
import inspect

from app.services.cover_storage import CoverStorageService


def _sql() -> str:
    return inspect.getsource(CoverStorageService.cleanup_lru)


def test_library_records_are_never_evicted():
    """Коллекция и вишлист — личная библиотека и самый посещаемый экран."""
    src = _sql()
    assert "CollectionItem.record_id == Record.id" in src
    assert "WishlistItem.record_id == Record.id" in src
    assert "~in_library" in src, "фильтр объявлен, но не применён к выборке"


def test_signed_discogs_urls_are_never_evicted():
    """ГЛАВНОЕ. Подписанная ссылка Discogs протухает, self-heal получит 403,
    и обложка не вернётся никогда. Такие записи выселять нельзя в принципе."""
    src = _sql()
    assert 'like("%discogs.com%")' in src
    assert "~Record.cover_image_url.like" in src, "условие должно ИСКЛЮЧАТЬ такие записи"


def test_record_without_external_url_is_not_evicted():
    """Без внешнего адреса восстановиться неоткуда — файл единственная копия."""
    assert "Record.cover_image_url.isnot(None)" in _sql()


def test_user_photos_still_protected():
    """Старая гарантия не должна потеряться при правке соседних условий:
    загруженное юзером фото невосстановимо."""
    assert 'Record.source.is_distinct_from("user")' in _sql()


def test_market_visible_still_protected():
    """И вторая старая гарантия — товары маркета (WS1.3)."""
    assert "~active_in_stock" in _sql()


def test_heal_script_avoids_discogs():
    """Лечилка не должна ходить в Discogs: его подписанные ссылки и создали
    проблему, повторно опираться на них бессмысленно."""
    from app.scripts import heal_lost_covers
    src = inspect.getsource(heal_lost_covers.heal)
    assert "discogs_probe=None" in src


def test_heal_targets_the_exact_symptom():
    """Признак потери: blurhash есть, файла нет. Другого способа отличить
    «удалили» от «никогда не качали» у нас нет."""
    from app.scripts import heal_lost_covers
    src = inspect.getsource(heal_lost_covers._candidates)
    assert "blurhash IS NOT NULL" in src
    assert "cover_local_path IS NULL" in src
    assert "in_library DESC" in src, "библиотечные лечим первыми — их видно людям"
