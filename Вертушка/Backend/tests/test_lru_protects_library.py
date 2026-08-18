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


def test_restore_uses_the_record_own_source_not_a_guess():
    """Лечилка обязана брать источник ИЗ ЗАПИСИ, а не искать заново.

    Первая версия (`heal_lost_covers`, удалена) прогоняла общую лестницу
    источников и подменила сканы конкретных прессов на album-level арт
    стриминга: 119 пластинок, у Tatsuro Yamashita вместо японского конверта с
    оби приехал CAA, у Baile и Ryo Fukui — Deezer 1000x1000.

    Ошибка была в выборе инструмента: лестница создана искать обложку там, где
    её НЕТ. Здесь обложка БЫЛА, и точный ответ лежал в records.cover_image_url.
    """
    from app.scripts import restore_pressing_covers as rp
    src = inspect.getsource(rp._fresh_url)
    assert "orig" in src, "источник берётся из записи, а не резолвится заново"
    assert "resolve_cover_url" not in src, "общая лестница здесь запрещена"
    assert "get_release_cover" in src, "для протухшей подписи Discogs — свежая по тому же id"


def test_restore_busts_stale_discogs_cache():
    """Без сброса кэша get_release_cover честно вернёт ту же мёртвую подпись —
    в кэше лежит payload релиза с уже протухшей ссылкой."""
    from app.scripts import restore_pressing_covers as rp
    src = inspect.getsource(rp._fresh_url)
    assert "cache.delete" in src
    assert '"release"' in src and '"release_cover"' in src


def test_restore_deletes_bad_file_before_redownload():
    """download_and_store видит существующий файл и уходит по короткому пути —
    подменённый файл надо снести заранее, иначе откат ничего не изменит."""
    from app.scripts import restore_pressing_covers as rp
    src = inspect.getsource(rp.restore)
    assert "unlink(missing_ok=True)" in src
    # Сравниваем позиции РЕАЛЬНОГО вызова, а не первого упоминания: имя метода
    # встречается ещё и в комментарии выше.
    assert src.index("unlink(missing_ok=True)") < src.index("await service.download_and_store")


def test_restore_set_is_frozen_in_a_table():
    """Набор пострадавших зафиксирован снапшотом, а не запросом по времени:
    фоновые джобы трогают те же поля, и окно поплыло бы."""
    from app.scripts import restore_pressing_covers as rp
    assert rp.TABLE == "cover_heal_rollback"
    assert "NOT restored" in inspect.getsource(rp._pending)
