"""Обложки на публичной веб-странице профиля.

Две болячки, которые тут закреплены.

1. Ручной релиз с фото показывался заглушкой: снимок лежит только на диске
   (`cover_local_path`), `cover_image_url` у такой записи пустой. В API путь
   разворачивает схема RecordResponse, а веб читал поле напрямую.

2. Обложки мерцали на скролле: в профиле под сотню картинок, и все грузились
   с i.discogs.com в 600×600 при ячейке ~200–330 px. 600×600 — это 1,4 МБ
   распакованных пикселей на штуку, на сотне обложек браузер начинает
   выбрасывать декодированное за экраном и декодировать заново при возврате.
"""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.web.routes import cover_url

API = get_settings().public_api_base
TPL = Path("app/web/templates/public_profile.html")


def rec(**kw):
    base = dict(cover_local_path=None, cover_image_url=None, cover_cached_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestCoverUrl:
    def test_local_cover_wins_over_empty_external(self):
        """Ручной релиз: фото есть только на диске."""
        url = cover_url(rec(cover_local_path="covers/user_abc.jpg"), 400)
        assert url == f"{API}/covers/w/400/user_abc.jpg"

    def test_local_cover_is_resized(self):
        """Нарезка под ячейку — то, ради чего всё затевалось."""
        assert "/covers/w/300/" in cover_url(rec(cover_local_path="covers/123.jpg"), 300)

    def test_without_width_serves_master(self):
        """Без ширины — мастер-файл тем же путём, что отдаёт API."""
        assert cover_url(rec(cover_local_path="covers/123.jpg")) == f"{API}/uploads/covers/123.jpg"

    def test_nested_path_is_not_resized(self):
        """nginx не пускает слэши в имени файла — вложенные отдаём как есть."""
        url = cover_url(rec(cover_local_path="covers/store/uuid.jpg"), 400)
        assert url == f"{API}/uploads/covers/store/uuid.jpg"

    def test_cache_bust_by_cached_at(self):
        ts = datetime(2026, 8, 15, 12, 0, 0)
        url = cover_url(rec(cover_local_path="covers/1.jpg", cover_cached_at=ts), 300)
        assert url.endswith(f"?v={int(ts.timestamp())}")

    def test_falls_back_to_external_url(self):
        """Зеркала нет — работает как раньше, ничего не ломаем."""
        ext = "https://i.discogs.com/xxx.jpeg"
        assert cover_url(rec(cover_image_url=ext), 400) == ext

    @pytest.mark.parametrize("record", [None, rec()])
    def test_no_cover_gives_empty_string(self, record):
        assert cover_url(record, 400) == ""


class TestTemplate:
    def test_template_never_reads_cover_field_directly(self):
        """Прямое обращение к полю — та самая ошибка, из-за которой ручные
        релизы теряли картинку. Ходить только через cover_url()."""
        assert "cover_image_url" not in TPL.read_text(encoding="utf-8")

    def test_grid_and_rails_ask_for_sized_covers(self):
        tpl = TPL.read_text(encoding="utf-8")
        assert "cover_url(item.record, 400)" in tpl, "сетка"
        assert "cover_url(r, 300)" in tpl, "рейлы"
        assert "cover_url(item.record, 600)" in tpl, "модалка"

    def test_images_decode_async(self):
        """Синхронное декодирование сотни картинок на скролле — это фризы."""
        tpl = TPL.read_text(encoding="utf-8")
        assert tpl.count('decoding="async"') >= 2


class TestRails:
    """Рейлы «Витрина» и «Маркет» строятся не из ORM-объектов, а через
    _record_to_public с явными kwargs. Забыть там поле легко, а заметно это
    только по тому, что карусели грузят оригиналы мимо зеркала."""

    def test_public_record_gets_mirror_path(self):
        from app.api.profile import _record_to_public

        record = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            title="T", artist="A", year=None, label=None, format_type=None,
            cover_image_url="https://i.discogs.com/x.jpeg",
            thumb_image_url=None,
            cover_local_path="covers/42.jpg",
            cover_cached_at=datetime(2026, 8, 15, 10, 0, 0),
            estimated_price_median=None, estimated_price_min=None,
            price_currency="USD", discogs_id="42", discogs_master_id=None,
            is_first_press=False, is_canon=False, is_collectible=False,
            is_limited=False, is_hot=False,
        )
        pub = _record_to_public(record)
        assert pub.cover_local_path == "covers/42.jpg"
        assert pub.cover_cached_at is not None
        # и веб соберёт из этого нарезку
        assert "/covers/w/300/42.jpg" in cover_url(pub, 300)

    def test_mirror_path_never_leaks_to_json(self):
        from app.api.profile import _record_to_public

        record = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            title="T", artist="A", year=None, label=None, format_type=None,
            cover_image_url=None, thumb_image_url=None,
            cover_local_path="covers/user_secret.jpg", cover_cached_at=None,
            estimated_price_median=None, estimated_price_min=None,
            price_currency="USD", discogs_id=None, discogs_master_id=None,
            is_first_press=False, is_canon=False, is_collectible=False,
            is_limited=False, is_hot=False,
        )
        dumped = _record_to_public(record).model_dump()
        assert "cover_local_path" not in dumped
        assert "cover_cached_at" not in dumped


class TestSchema:
    def test_public_record_carries_local_path_but_hides_it(self):
        """Рейлам поле нужно, наружу отдавать внутренние пути не нужно."""
        from app.schemas.profile import PublicProfileRecord

        fields = PublicProfileRecord.model_fields
        assert "cover_local_path" in fields
        assert fields["cover_local_path"].exclude is True
        assert fields["cover_cached_at"].exclude is True
