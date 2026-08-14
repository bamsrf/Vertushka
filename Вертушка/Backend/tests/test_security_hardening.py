"""Регресс-тесты на находки из docs/plans/SECURITY_AUDIT_PRERELEASE.md.

Каждый тест привязан к конкретному §: если он покраснел — вернулась именно та
дыра, а не «что-то похожее».
"""
import asyncio
from pathlib import Path

import pytest
from markupsafe import Markup


# ── §S1: stored XSS в fun-stats публичного профиля ──────────────────────────

# Короткие полезные нагрузки: обрезка имени артиста до 18/22 символов, которая
# стояла вместо экранирования, их не ломает.
XSS_PAYLOADS = [
    "<svg onload=alert(1)>",
    "<base href=//evil.ru>",
    "<script src=//evil.ru>",
    '"><img src=x onerror=alert(1)>',
]


@pytest.fixture(scope="module")
def jinja_env():
    from fastapi.templating import Jinja2Templates

    return Jinja2Templates(directory="app/web/templates").env


def test_autoescape_enabled(jinja_env):
    """Снятие |safe имеет смысл только при включённом автоэкранировании."""
    assert jinja_env.autoescape is True


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_fun_stat_markup_escapes_payload(jinja_env, payload):
    """Markup(...).format() экранирует подстановку, свою разметку сохраняет."""
    tpl = jinja_env.from_string("<span>{{ stat.html }}</span>")
    stat = {"html": Markup("Топ-артист: <b>{}</b>").format(payload)}

    rendered = tpl.render(stat=stat)

    assert payload not in rendered, "полезная нагрузка попала в разметку как есть"
    assert "&lt;" in rendered, "подстановка не экранирована"
    assert "<b>" in rendered, "собственная разметка стата потерялась"


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_plain_string_stat_is_escaped_not_executed(jinja_env, payload):
    """Fail-safe: забытый Markup даёт видимые теги, а не исполнение.

    Ради этого из шаблона убран |safe. Пока он там стоял, обычная f-строка
    (как было в routes.py) уезжала в страницу без единой проверки.
    """
    tpl = jinja_env.from_string("<span>{{ stat.html }}</span>")

    rendered = tpl.render(stat={"html": f"Топ-артист: <b>{payload}</b>"})

    assert payload not in rendered
    assert "<b>" not in rendered


def test_template_has_no_safe_filter():
    """В public_profile.html не должно быть |safe ни в одном выражении."""
    html = Path("app/web/templates/public_profile.html").read_text(encoding="utf-8")
    expressions = [
        line for line in html.splitlines()
        if "|safe" in line and "{#" not in line and not line.strip().startswith("#")
    ]
    assert not expressions, f"вернулся |safe: {expressions}"


def test_routes_build_stats_via_markup():
    """В routes.py не должно остаться `"html": f"..."` — только Markup."""
    src = Path("app/web/routes.py").read_text(encoding="utf-8")
    assert '"html": f"' not in src, "fun-stat снова собирается f-строкой"


# ── §S2: mass assignment / открытый редирект / SSRF ─────────────────────────


def test_manual_record_creation_endpoint_is_gone():
    """POST /api/records/ splat'ил вход в модель мимо модерации — удалён.

    Легальный путь для пользовательских записей — POST /api/records/user/.
    """
    from app.main import app

    posts = {
        r.path for r in app.routes
        if getattr(r, "methods", None) and "POST" in r.methods
    }
    assert "/api/records/" not in posts
    assert "/api/records/user/" in posts, "модерируемый путь должен остаться"


def test_record_create_schema_unused():
    """RecordCreate не должна использоваться ни одним эндпоинтом."""
    src = Path("app/api/records.py").read_text(encoding="utf-8")
    code = [
        line for line in src.splitlines()
        if "RecordCreate" in line
        and "UserRecordCreate" not in line
        and not line.strip().startswith("#")
    ]
    assert not code, f"RecordCreate вернулась в код: {code}"


INTERNAL_TARGETS = [
    "http://redis:6379/",
    "http://imgproxy:8080/",
    "http://postgres:5432/",
    "http://127.0.0.1:8000/",
    "http://localhost/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://172.17.0.1/",
    "http://[::1]/",
]

BAD_SCHEMES = ["file:///etc/passwd", "gopher://x/", "javascript:alert(1)", "ftp://x/y"]


@pytest.mark.parametrize("url", INTERNAL_TARGETS)
def test_assert_safe_url_blocks_internal(url):
    from app.utils.url_guard import UnsafeUrlError, assert_safe_url

    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_safe_url(url))


@pytest.mark.parametrize("url", BAD_SCHEMES)
def test_assert_safe_url_blocks_non_http(url):
    from app.utils.url_guard import UnsafeUrlError, assert_safe_url

    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_safe_url(url))


def test_assert_safe_url_blocks_credentials():
    from app.utils.url_guard import UnsafeUrlError, assert_safe_url

    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_safe_url("http://user:pw@example.com/x.jpg"))


@pytest.mark.parametrize(
    "url",
    [
        "https://shop.example.ru/covers/1.jpg",
        "https://i.discogs.com/x.jpg",
        "http://cdn.example.com/a.png",
    ],
)
def test_redirect_guard_allows_external(url):
    from app.utils.url_guard import is_safe_redirect_target

    assert is_safe_redirect_target(url) is True


@pytest.mark.parametrize(
    "url",
    BAD_SCHEMES
    + [None, "", "not a url", "http://user:pw@example.com/x.jpg"]
    # Литеральные внутренние адреса — их гард видит без резолва.
    + [
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.17.0.1/",
        "http://[::1]/",
    ],
)
def test_redirect_guard_rejects_unsafe(url):
    """Гард для 302, которые уходят КЛИЕНТУ.

    Главное, что он ловит, — не-http схемы: `javascript:` в Location это XSS,
    а `data:` — фишинговая страница на нашем домене в истории браузера.
    Плюс креды в URL и литеральные внутренние адреса.

    Чего он намеренно НЕ делает — резолва DNS. `http://redis:6379/` он
    пропустит, и это осознанно: браузер клиента до нашего redis всё равно не
    достучится, а вот серверную закачку по тому же URL останавливает
    assert_safe_url (см. тесты выше). Разделение ролей, а не пробел.
    """
    from app.utils.url_guard import is_safe_redirect_target

    assert is_safe_redirect_target(url) is False


@pytest.mark.parametrize("url", ["http://redis:6379/", "http://imgproxy:8080/"])
def test_redirect_guard_defers_hostnames_to_async_guard(url):
    """Фиксируем разделение ролей из докстринга выше, чтобы оно не «уехало»."""
    from app.utils.url_guard import (
        UnsafeUrlError,
        assert_safe_url,
        is_safe_redirect_target,
    )

    # Синхронный гард пропускает — ему хватает того, что это http и не IP.
    assert is_safe_redirect_target(url) is True
    # А серверная закачка по тому же URL не состоится.
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_safe_url(url))


def test_cover_download_goes_through_guard():
    """Обе точки закачки обложек обязаны звать safe_image_get, не httpx напрямую."""
    src = Path("app/services/cover_storage.py").read_text(encoding="utf-8")
    assert "follow_redirects=True" not in src, (
        "httpx сам разматывает редиректы — проверка первого хопа обесценивается"
    )
    assert src.count("safe_image_get(") >= 2


# ── §S3: вычистка удалённых аккаунтов ───────────────────────────────────────


def test_purge_job_registered_in_scheduler():
    """Джоба должна быть заведена в main.py, иначе вычистки не происходит."""
    src = Path("app/main.py").read_text(encoding="utf-8")
    assert "purge_deleted_users" in src
    assert "id='purge_deleted_users'" in src


def test_purge_removes_user_photos_and_avatar(tmp_path, monkeypatch):
    """Каскады чистят строки; JPEG'и надо удалять руками — и фото, и аватар."""
    from app.scripts import purge_deleted_users as mod

    user_id = "11111111-1111-1111-1111-111111111111"
    photos_root = tmp_path / "user_photos"
    avatars_root = tmp_path / "avatars"
    user_dir = photos_root / user_id
    user_dir.mkdir(parents=True)
    (user_dir / "a.jpg").write_bytes(b"x")
    (user_dir / "b.jpg").write_bytes(b"y")
    avatars_root.mkdir(parents=True)
    avatar = avatars_root / f"{user_id}.jpg"
    avatar.write_bytes(b"z")

    monkeypatch.setattr(mod, "_USER_PHOTOS_ROOT", photos_root)
    monkeypatch.setattr(mod, "_AVATARS_ROOT", avatars_root)

    removed = mod._drop_user_files(user_id)

    assert removed == 3
    assert not user_dir.exists()
    assert not avatar.exists()


def test_purge_does_not_touch_other_users(tmp_path, monkeypatch):
    """Удаляем ровно одного — соседи по каталогу остаются на месте."""
    from app.scripts import purge_deleted_users as mod

    doomed = "11111111-1111-1111-1111-111111111111"
    bystander = "99999999-9999-9999-9999-999999999999"
    photos_root = tmp_path / "user_photos"
    avatars_root = tmp_path / "avatars"
    for uid in (doomed, bystander):
        (photos_root / uid).mkdir(parents=True)
        (photos_root / uid / "a.jpg").write_bytes(b"x")
    avatars_root.mkdir(parents=True)
    (avatars_root / f"{doomed}.jpg").write_bytes(b"z")
    (avatars_root / f"{bystander}.jpg").write_bytes(b"z")

    monkeypatch.setattr(mod, "_USER_PHOTOS_ROOT", photos_root)
    monkeypatch.setattr(mod, "_AVATARS_ROOT", avatars_root)

    mod._drop_user_files(doomed)

    assert (photos_root / bystander / "a.jpg").exists()
    assert (avatars_root / f"{bystander}.jpg").exists()


def test_purge_file_cleanup_is_idempotent(tmp_path, monkeypatch):
    """Нет ни фото, ни аватара — не падаем."""
    from app.scripts import purge_deleted_users as mod

    monkeypatch.setattr(mod, "_USER_PHOTOS_ROOT", tmp_path / "user_photos")
    monkeypatch.setattr(mod, "_AVATARS_ROOT", tmp_path / "avatars")

    assert mod._drop_user_files("22222222-2222-2222-2222-222222222222") == 0


def test_purge_module_does_not_hijack_root_logger():
    """basicConfig на уровне модуля затирал бы JSON-хендлер из main.py."""
    src = Path("app/scripts/purge_deleted_users.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        if "basicConfig" in line:
            assert line.startswith("    "), (
                "basicConfig должен вызываться только под if __name__ == '__main__'"
            )
