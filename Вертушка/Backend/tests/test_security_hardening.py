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
