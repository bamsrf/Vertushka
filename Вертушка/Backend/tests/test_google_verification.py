"""Подтверждение владения доменом для Google Search Console.

Зачем оно вообще: 2026-08-15 Chrome начал показывать на /support плашку
«опасный сайт». Это Safe Browsing — репутация URL, а не TLS (сам браузер
рядом писал, что сертификат валиден). Причину вердикта и статус заявки на
пересмотр видно только в Search Console, а туда пускают лишь после
подтверждения владения.

Файл нельзя выложить один раз и забыть: Google перепроверяет владение и
молча снимает права, если файл пропал. Поэтому это маршрут в коде, а не
подкладка на сервере, — и поэтому у него есть тест.
"""
import pytest

from app.config import get_settings

TOKEN = get_settings().google_site_verification


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)  # без `with` — lifespan не нужен


@pytest.mark.parametrize("path", ["/{}", "/support/{}"])
def test_verification_file_is_served(client, path):
    """Search Console берёт файл по адресу подтверждаемого префикса.

    Свойство заведено на /support/, но корень отдаём тоже: подтверждение
    домена целиком — следующий шаг, и ради него не должно понадобиться
    выкатывать код заново.
    """
    r = client.get(path.format(TOKEN))
    assert r.status_code == 200
    assert r.text == f"google-site-verification: {TOKEN}"


def test_content_matches_googles_own_format(client):
    """Google сверяет содержимое дословно. Лишний перевод строки или
    отличающееся имя — «не удалось подтвердить» без объяснений."""
    body = client.get(f"/{TOKEN}").text
    assert body.startswith("google-site-verification: ")
    assert body.endswith(".html")
    assert "\n" not in body


def test_token_looks_like_a_google_filename():
    assert TOKEN.startswith("google") and TOKEN.endswith(".html")


def test_verification_is_not_in_public_schema():
    """Служебный маршрут в /docs — шум, к API он отношения не имеет."""
    from app.main import app

    for route in app.routes:
        if getattr(route, "path", "") == f"/{TOKEN}":
            assert route.include_in_schema is False
            return
    pytest.fail("маршрут подтверждения не зарегистрирован")
