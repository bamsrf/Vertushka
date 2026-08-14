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


# ── §S4: JWT после переезда python-jose → PyJWT ─────────────────────────────
#
# Библиотеку на критическом пути аутентификации меняли целиком, поэтому тут
# проверяются свойства, а не вызовы: важно не «зовём ли мы PyJWT», а
# «отвергается ли то, что должно отвергаться».


def test_jose_is_gone():
    """python-jose не должен остаться ни в коде, ни в зависимостях."""
    # Только строки-зависимости: в комментариях jose упоминается намеренно,
    # там объяснено, почему от него ушли.
    requirements = [
        line.strip()
        for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not [r for r in requirements if r.lower().startswith("python-jose")]
    assert any(r.startswith("PyJWT") for r in requirements)

    for path in ("app/utils/security.py", "app/api/auth.py"):
        code = [
            line
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("#")
        ]
        assert not [line for line in code if "from jose" in line or "import jose" in line]


def test_token_round_trip():
    import uuid

    from app.utils.security import create_access_token, decode_token

    uid = uuid.uuid4()
    payload = decode_token(create_access_token(uid, token_version=7))

    assert payload["sub"] == str(uid)
    assert payload["type"] == "access"
    assert payload["tv"] == 7


def test_token_type_is_enforced():
    """Access-токен не должен проходить там, где ждут refresh, и наоборот."""
    import uuid

    from app.utils.security import (
        create_access_token,
        create_refresh_token,
        verify_token_type,
    )

    uid = uuid.uuid4()
    access = create_access_token(uid)
    refresh = create_refresh_token(uid)

    assert verify_token_type(access, "access") is not None
    assert verify_token_type(access, "refresh") is None
    assert verify_token_type(refresh, "refresh") is not None
    assert verify_token_type(refresh, "access") is None


def test_token_signed_with_foreign_key_rejected():
    import uuid
    from datetime import datetime, timedelta

    import jwt as pyjwt

    from app.utils.security import decode_token

    forged = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "tv": 0,
            "exp": datetime.utcnow() + timedelta(hours=1),
        },
        "attacker-key-" + "x" * 40,
        algorithm="HS256",
    )
    assert decode_token(forged) is None


def test_alg_none_token_rejected():
    """Классический обход: подпись выброшена, alg=none."""
    import uuid

    import jwt as pyjwt

    from app.utils.security import decode_token

    unsigned = pyjwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "tv": 0}, key="", algorithm="none",
    )
    assert decode_token(unsigned) is None


def test_expired_token_rejected():
    import uuid
    from datetime import datetime, timedelta

    import jwt as pyjwt

    from app.config import get_settings
    from app.utils.security import decode_token

    expired = pyjwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "tv": 0,
            "exp": datetime.utcnow() - timedelta(seconds=5),
        },
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    assert decode_token(expired) is None


@pytest.mark.parametrize("garbage", ["", "not.a.token", "a.b.c", "....", "null"])
def test_garbage_token_rejected(garbage):
    from app.utils.security import decode_token

    assert decode_token(garbage) is None


@pytest.fixture(scope="module")
def apple_jwks_setup():
    """Настоящая RSA-пара + JWKS, как отдаёт Apple. Проверяет PyJWK —
    самое крупное отличие API от jose.jwk.construct."""
    import json

    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    pub.update({"kid": "test-kid-1", "alg": "RS256", "use": "sig"})
    return key, pub


def _apple_token(key, **overrides):
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    claims = {
        "iss": "https://appleid.apple.com",
        "aud": "com.vertushka.app",
        "sub": "apple-user-123",
        "email": "u@privaterelay.appleid.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    claims.update(overrides)
    return pyjwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-kid-1"})


@pytest.fixture
def apple_auth(monkeypatch, apple_jwks_setup):
    import app.api.auth as auth_mod

    key, pub = apple_jwks_setup
    monkeypatch.setenv("APPLE_CLIENT_ID", "com.vertushka.app")

    async def _fake_jwks():
        return {"keys": [pub]}

    monkeypatch.setattr(auth_mod, "_get_apple_jwks", _fake_jwks)

    from app.config import Settings

    def _settings():
        return Settings(DEBUG=True, APPLE_CLIENT_ID="com.vertushka.app")

    monkeypatch.setattr(auth_mod, "get_settings", _settings)
    return auth_mod, key


def test_apple_valid_token_accepted(apple_auth):
    auth_mod, key = apple_auth

    payload = asyncio.run(auth_mod._verify_apple_identity_token(_apple_token(key)))

    assert payload["sub"] == "apple-user-123"
    assert payload["email"] == "u@privaterelay.appleid.com"


def test_apple_rejects_foreign_audience(apple_auth):
    from fastapi import HTTPException

    auth_mod, key = apple_auth
    with pytest.raises(HTTPException):
        asyncio.run(
            auth_mod._verify_apple_identity_token(_apple_token(key, aud="com.attacker.app"))
        )


def test_apple_rejects_foreign_issuer(apple_auth):
    from fastapi import HTTPException

    auth_mod, key = apple_auth
    with pytest.raises(HTTPException):
        asyncio.run(
            auth_mod._verify_apple_identity_token(_apple_token(key, iss="https://evil.com"))
        )


def test_apple_rejects_expired(apple_auth):
    from datetime import datetime, timedelta, timezone

    from fastapi import HTTPException

    auth_mod, key = apple_auth
    stale = _apple_token(key, exp=datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(HTTPException):
        asyncio.run(auth_mod._verify_apple_identity_token(stale))


def test_apple_rejects_token_signed_by_other_key(apple_auth):
    """Главное свойство JWKS-проверки: kid совпал, ключ — нет."""
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import HTTPException

    auth_mod, _ = apple_auth
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = pyjwt.encode(
        {
            "iss": "https://appleid.apple.com",
            "aud": "com.vertushka.app",
            "sub": "victim",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        attacker,
        algorithm="RS256",
        headers={"kid": "test-kid-1"},
    )
    with pytest.raises(HTTPException):
        asyncio.run(auth_mod._verify_apple_identity_token(forged))


def test_apple_rejects_alg_none(apple_auth):
    import jwt as pyjwt
    from fastapi import HTTPException

    auth_mod, _ = apple_auth
    unsigned = pyjwt.encode(
        {"iss": "https://appleid.apple.com", "aud": "com.vertushka.app", "sub": "x"},
        key="",
        algorithm="none",
    )
    with pytest.raises(HTTPException):
        asyncio.run(auth_mod._verify_apple_identity_token(unsigned))


# ── §S7/§S8/§S12: сброс пароля ──────────────────────────────────────────────


def test_reset_code_uses_csprng():
    """random (Mersenne Twister) предсказуем по наблюдаемым выходам."""
    auth_src = Path("app/api/auth.py").read_text(encoding="utf-8")
    code_lines = [
        line for line in auth_src.splitlines() if not line.strip().startswith("#")
    ]
    assert not [line for line in code_lines if "random.randint" in line]
    assert not [line for line in code_lines if "import random" in line]
    assert "secrets.randbelow" in auth_src


def test_reset_code_shape():
    from app.api.auth import _generate_reset_code

    codes = {_generate_reset_code() for _ in range(200)}
    for code in codes:
        assert len(code) == 6 and code.isdigit(), code
    # 200 бросков из миллиона — совпадений быть практически не должно.
    assert len(codes) > 190, "подозрительно мало уникальных кодов"


def test_reset_code_covers_low_values():
    """Ведущие нули не должны теряться: 42 → '000042', а не '42'."""
    from app.api.auth import _generate_reset_code

    assert all(len(_generate_reset_code()) == 6 for _ in range(500))


def _code_only(source: str) -> str:
    """Исполняемые строки без комментариев и докстрингов.

    Нужно потому, что в докстрингах намеренно процитировано то, что удалено
    («Осталось попыток: N») — иначе тест ловит собственное объяснение.
    """
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        # Докстринги — первый строковый Expr в модуле/классе/функции.
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    body[0].value.value = ""
    return ast.unparse(tree)


def test_verify_reset_code_has_single_error_message():
    """Разные тексты ошибок были прямым оракулом на существование email."""
    import ast

    src = Path("app/api/auth.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "verify_reset_code"
    )
    body = _code_only(ast.unparse(func))

    # «Осталось попыток: N» подтверждало, что аккаунт есть и код по нему запрошен.
    assert "Осталось попыток" not in body
    # Отдельный 429 подтверждал то же самое.
    assert "HTTP_429_TOO_MANY_REQUESTS" not in body
    # Все отказы идут через один хелпер с одним текстом.
    assert body.count("raise _reject()") >= 4


def test_forgot_password_equalises_timing():
    """Ветка «юзера нет» обязана стоить столько же, сколько ветка «есть».

    Иначе bcrypt (~200мс) и ожидание Resend в одной из веток выдают наличие
    аккаунта разницей времени ответа на порядок.
    """
    src = Path("app/api/auth.py").read_text(encoding="utf-8")
    start = src.index("async def forgot_password")
    body = src[start : start + 2200]

    assert "_DUMMY_RESET_HASH" in body, "нет выравнивания стоимости bcrypt"
    assert "asyncio.create_task" in body, "письмо шлётся синхронно — задержка видна"


def test_reset_token_carries_jti():
    """Одноразовость держится на jti; без него токен переиспользуем."""
    src = Path("app/api/auth.py").read_text(encoding="utf-8")
    start = src.index("async def verify_reset_code")
    body = src[start : src.index("@router.post(\"/reset-password/\")")]

    assert '"jti": jti' in body
    assert "user.reset_token_jti = jti" in body
    assert "secrets.token_urlsafe" in body


def test_reset_password_consumes_jti():
    src = Path("app/api/auth.py").read_text(encoding="utf-8")
    start = src.index("async def reset_password")
    body = src[start : start + 2600]

    assert "secrets.compare_digest" in body, "сравнение jti должно быть постоянного времени"
    assert "user.reset_token_jti = None" in body, "токен не гасится после использования"


def test_reset_token_jti_column_exists():
    from app.models.user import User

    assert hasattr(User, "reset_token_jti")


def test_migration_chain_has_single_head():
    """Новая миграция не должна расщепить историю на две головы.

    Через ScriptDirectory, а не парсингом: в истории есть merge-ревизии, где
    down_revision — кортеж, и наивный разбор строк насчитывает лишние головы.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = list(script.get_heads())

    assert heads == ["20260814_reset_jti"], f"голов должно быть одна, найдено: {heads}"


def test_password_reset_log_has_no_email():
    """PII в структурированном логе живут в ротации и в сборщике (§S14)."""
    src = Path("app/api/auth.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        if "password_reset" in line and "logger" in line:
            assert "email" not in line, line


# ── §S10: загрузка фотографий ───────────────────────────────────────────────


def _png_bytes(width: int, height: int) -> bytes:
    """Одноцветный PNG: сжимается в килобайты при любом разрешении."""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("L", (width, height), 0).save(buf, "PNG", compress_level=9)
    return buf.getvalue()


def test_decompression_bomb_rejected():
    """900 Мп в файле на ~850 КБ: лимит размера файла тут бессилен."""
    from fastapi import HTTPException

    from app.api.user_photos import decode_user_photo

    bomb = _png_bytes(30000, 30000)
    assert len(bomb) < 10 * 1024 * 1024, "бомба должна проходить лимит размера файла"

    with pytest.raises(HTTPException) as exc:
        decode_user_photo(bomb)
    assert exc.value.status_code == 422


def test_bomb_between_limit_and_double_limit_rejected():
    """Промежуток, который Pillow пропускает с одним лишь предупреждением.

    DecompressionBombError срабатывает только на удвоенном MAX_IMAGE_PIXELS,
    поэтому при лимите 40 Мп картинка на 56 Мп (файл ~50 КБ) проходила бы
    молча. Её ловит явная проверка по заголовку.
    """
    from fastapi import HTTPException

    from app.api.user_photos import _MAX_PIXELS, decode_user_photo

    width = height = 7500
    assert _MAX_PIXELS < width * height < _MAX_PIXELS * 2, "тест потерял смысл"

    with pytest.raises(HTTPException) as exc:
        decode_user_photo(_png_bytes(width, height))
    assert exc.value.status_code == 422


@pytest.mark.parametrize("size", [(1200, 1200), (4000, 3000), (800, 600)])
def test_normal_photos_still_accepted(size):
    from app.api.user_photos import decode_user_photo

    img = decode_user_photo(_png_bytes(*size))
    assert img.size == size
    assert img.mode == "RGB"


def test_global_pillow_limit_is_restored():
    """MAX_IMAGE_PIXELS — настройка модуля; менять её насовсем нельзя."""
    from PIL import Image
    from fastapi import HTTPException

    from app.api.user_photos import decode_user_photo

    before = Image.MAX_IMAGE_PIXELS
    decode_user_photo(_png_bytes(100, 100))
    assert Image.MAX_IMAGE_PIXELS == before

    with pytest.raises(HTTPException):
        decode_user_photo(_png_bytes(30000, 30000))
    assert Image.MAX_IMAGE_PIXELS == before, "лимит не восстановлен после ошибки"


def test_garbage_upload_rejected():
    from fastapi import HTTPException

    from app.api.user_photos import decode_user_photo

    with pytest.raises(HTTPException) as exc:
        decode_user_photo(b"this is definitely not an image")
    assert exc.value.status_code == 422


def test_upload_reads_with_ceiling_not_after():
    """`await file.read()` без аргумента тянет тело целиком в память."""
    src = Path("app/api/user_photos.py").read_text(encoding="utf-8")
    assert "await file.read(limit + 1)" in src
    assert "raw = await file.read()" not in src


def test_upload_has_per_user_quota():
    src = Path("app/api/user_photos.py").read_text(encoding="utf-8")
    assert "_MAX_PHOTOS_PER_USER" in src
    quota_at = src.index("_MAX_PHOTOS_PER_USER:")
    write_at = src.index("img.save(tmp_path")
    assert quota_at < write_at, "квота должна проверяться до записи файла"


# ── §S9/§S11/§S13/§S15/§S16: конфиг nginx ───────────────────────────────────
#
# Проверки текстовые: nginx в CI нет. Синтаксис и реальные заголовки
# проверялись throwaway-контейнером (`docker run --rm nginx:alpine nginx -t`
# плюс curl по каждому location) — эти тесты стерегут, чтобы правки не уехали.


@pytest.fixture(scope="module")
def nginx_conf():
    return Path("nginx/nginx.conf").read_text(encoding="utf-8")


def _location_blocks(conf: str) -> list[tuple[int, str, str, str]]:
    """Нарезка на location-блоки: (номер строки, server_name, заголовок, тело).

    Список, а не словарь: `location / {` встречается в конфиге восемь раз, и
    словарь схлопывал бы их в одну запись — тест молча перестал бы проверять
    все, кроме последней. Ровно на этом он и попался в первой версии.

    server_name нужен, чтобы отличать наши домены от посторонних блоков в том
    же файле (на 443 этого сервера живут и чужие проекты).
    """
    blocks: list[tuple[int, str, str, str]] = []
    current: list[str] = []
    name, start, server = None, 0, "?"
    for lineno, line in enumerate(conf.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("server_name "):
            server = stripped[len("server_name ") :].rstrip(";")
        if stripped.startswith("location ") and stripped.endswith("{"):
            name, start, current = stripped, lineno, []
        elif name is not None:
            if stripped == "}":
                blocks.append((start, server, name, "\n".join(current)))
                name = None
            else:
                current.append(stripped)
    return blocks


# Домены Вертушки. Всё прочее в этом nginx.conf — соседние проекты на том же
# сервере, их конфиг живёт своей жизнью и правится вне этой работы.
_OUR_SERVERS = {"vinyl-vertushka.ru", "api.vinyl-vertushka.ru"}


def test_covers_locations_keep_security_headers(nginx_conf):
    """add_header в location ОТМЕНЯЕТ унаследованные из server.

    Проверено вживую: до фикса `/covers/1.jpg` с существующим файлом отдавался
    только с Cache-Control — без HSTS и nosniff.
    """
    checked = 0
    for lineno, server, name, body in _location_blocks(nginx_conf):
        if server not in _OUR_SERVERS or "add_header" not in body:
            continue  # чужой домен либо ничего не переопределяет
        where = f"строка {lineno}, {server}, {name}"
        assert "X-Content-Type-Options" in body, f"{where}: потерян nosniff"
        assert "Strict-Transport-Security" in body, f"{where}: потерян HSTS"
        checked += 1

    # Страховка от «тест позеленел, потому что ничего не нашёл».
    assert checked >= 7, f"проверено всего {checked} блоков — парсер что-то не увидел"


def test_csp_present_and_blocks_known_payloads(nginx_conf):
    """CSP должна гасить ровно те нагрузки, которыми эксплуатировался §S1."""
    assert "Content-Security-Policy" in nginx_conf
    csp = next(l for l in nginx_conf.splitlines() if "Content-Security-Policy" in l)

    assert "base-uri 'self'" in csp, "<base href=//x.ru> не заблокирован"
    assert "object-src 'none'" in csp
    assert "form-action 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    # script-src без wildcard — иначе <script src=//evil.ru> пройдёт.
    assert "script-src" in csp and "script-src *" not in csp


def test_deprecated_xss_header_removed(nginx_conf):
    """X-XSS-Protection устарел и в ряде браузеров сам был вектором (§S15)."""
    active = [
        line for line in nginx_conf.splitlines()
        if "X-XSS-Protection" in line and not line.strip().startswith("#")
    ]
    assert not active


def test_connection_upgrade_is_conditional(nginx_conf):
    """Безусловный Connection: upgrade на каждый запрос ломает keep-alive (§S16)."""
    assert "map $http_upgrade $connection_upgrade" in nginx_conf
    active = [
        line for line in nginx_conf.splitlines()
        if 'Connection "upgrade"' in line and not line.strip().startswith("#")
    ]
    assert not active, "остался литеральный Connection: upgrade"


def test_rate_limiting_configured(nginx_conf):
    """slowapi живёт в памяти процесса и обнуляется деплоем — нужен потолок на эдже."""
    assert "limit_req_zone" in nginx_conf
    assert "limit_req zone=api_general" in nginx_conf
    assert "limit_req zone=api_write" in nginx_conf
    assert "limit_conn api_conn" in nginx_conf


def test_ws_access_log_hides_query_string(nginx_conf):
    """Токен едет в query, дефолтный combined писал бы его на диск (§S9)."""
    assert "log_format ws_safe" in nginx_conf
    ws_format = next(l for l in nginx_conf.splitlines() if "log_format ws_safe" in l)
    # $request содержит query-строку целиком, $uri — нет.
    assert "$request " not in ws_format and "$request'" not in ws_format
    assert "$uri" in nginx_conf[nginx_conf.index("log_format ws_safe") :][:400]

    ws = next(
        (body for _, _, name, body in _location_blocks(nginx_conf) if "/api/messages/ws" in name),
        None,
    )
    assert ws is not None, "нет отдельного location для WS"
    assert "access_log" in ws and "ws_safe" in ws


# ── §S5: гейт на секреты при старте ─────────────────────────────────────────


def _settings(**overrides):
    """Settings с валидным прод-базисом, поверх которого кладём проверяемое."""
    from app.config import Settings

    base = {
        "DEBUG": False,
        "SECRET_KEY": "a" * 64,
        "JWT_SECRET_KEY": "b" * 64,
    }
    base.update(overrides)
    return Settings(**base)


def test_secret_gate_passes_on_proper_secrets():
    from app.config import assert_secrets_ok

    assert_secrets_ok(_settings())  # не бросает


@pytest.mark.parametrize(
    "value",
    [
        "change-me-in-production",
        "your-jwt-secret-key-change-in-production",
        "test-secret",
        "",
        "short",
    ],
)
def test_secret_gate_rejects_weak_jwt_secret(value):
    from app.config import InsecureConfigError, assert_secrets_ok

    with pytest.raises(InsecureConfigError):
        assert_secrets_ok(_settings(JWT_SECRET_KEY=value))


def test_secret_gate_rejects_weak_app_secret():
    from app.config import InsecureConfigError, assert_secrets_ok

    with pytest.raises(InsecureConfigError):
        assert_secrets_ok(_settings(SECRET_KEY="change-me-in-production"))


def test_secret_gate_is_off_in_debug():
    """Локальная разработка и тесты не должны требовать настоящих секретов."""
    from app.config import assert_secrets_ok

    assert_secrets_ok(_settings(DEBUG=True, JWT_SECRET_KEY="x", SECRET_KEY="x"))


def test_secret_gate_message_leaks_no_values():
    """Сообщение уходит в docker-логи — значений конфига в нём быть не должно.

    Ради этого проверка вынесена из pydantic-валидатора: ValidationError
    печатает input_value со срезом конфига.
    """
    from app.config import InsecureConfigError, assert_secrets_ok

    real = "REAL-SECRET-VALUE-must-not-appear-in-logs"
    with pytest.raises(InsecureConfigError) as exc:
        assert_secrets_ok(_settings(SECRET_KEY=real, JWT_SECRET_KEY="change-me-in-production"))

    message = str(exc.value)
    assert real not in message
    assert "change-me-in-production" not in message
    assert "SECRET_KEY" in message  # имя переменной назвать можно и нужно


def test_main_calls_secret_gate_before_app_creation():
    """Гейт должен стоять до FastAPI(...), иначе процесс успеет подняться."""
    src = Path("app/main.py").read_text(encoding="utf-8")
    assert "assert_secrets_ok()" in src
    assert src.index("assert_secrets_ok()") < src.index("app = FastAPI(")


# ── §S6: блокировка шире личных сообщений ───────────────────────────────────


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """Минимальная заглушка AsyncSession: отдаёт заранее заданный результат."""

    def __init__(self, block_row=None):
        self._block_row = block_row
        self.executed = []

    async def execute(self, stmt, *args, **kwargs):
        self.executed.append(stmt)
        return _FakeResult(self._block_row)


def test_is_user_blocked_detects_block():
    from app.services.blocking import is_user_blocked

    uid_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    uid_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    assert asyncio.run(is_user_blocked(_FakeSession(block_row="found"), uid_a, uid_b)) is True
    assert asyncio.run(is_user_blocked(_FakeSession(block_row=None), uid_a, uid_b)) is False


def test_is_user_blocked_short_circuits_self():
    """Сам себя не блокирует — и в БД за этим не ходим."""
    from app.services.blocking import is_user_blocked

    session = _FakeSession(block_row="found")
    uid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    assert asyncio.run(is_user_blocked(session, uid, uid)) is False
    assert session.executed == []


def test_block_check_is_bidirectional():
    """Неважно, кто кого заблокировал — в SQL должны быть обе комбинации."""
    src = Path("app/services/blocking.py").read_text(encoding="utf-8")
    assert "UserBlock.blocker_id == a_id" in src
    assert "UserBlock.blocker_id == b_id" in src


def test_notifications_suppressed_for_blocked_actor(monkeypatch):
    """Воронка уведомлений обязана отсекать заблокированного актора."""
    from app.services import notification_service as ns

    async def _blocked(db, a, b):
        return True

    monkeypatch.setattr(ns, "is_user_blocked", _blocked)

    notif, is_new = asyncio.run(
        ns.upsert_notification(
            _FakeSession(),
            user_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            type="follow",
            dedup_key="k",
            actor_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )
    )

    assert notif is None
    assert is_new is False


def test_notification_block_check_placed_in_funnel():
    """Проверка должна стоять в upsert_notification, а не в отдельных call-site.

    Иначе следующий тип уведомления добавят мимо неё.
    """
    src = Path("app/services/notification_service.py").read_text(encoding="utf-8")
    funnel = src.index("async def upsert_notification")
    check = src.index("is_user_blocked(db, user_id, actor_id)")
    self_guard = src.index("actor_id == user_id")
    assert funnel < check, "проверка блокировки вне воронки"
    assert self_guard < check < self_guard + 900, "проверка уехала далеко от guard'а на self"


def test_follow_endpoint_checks_block():
    src = Path("app/api/users.py").read_text(encoding="utf-8")
    follow_at = src.index("async def follow_user")
    tail = src[follow_at : follow_at + 2000]
    assert "is_user_blocked(db, current_user.id, user_id)" in tail


def test_blocking_severs_existing_follows():
    """Блокировка обязана рвать связь, а не только глушить уведомления."""
    src = Path("app/api/messages.py").read_text(encoding="utf-8")
    assert "Follow.__table__.delete()" in src
    assert "FollowRequest.__table__.delete()" in src


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
