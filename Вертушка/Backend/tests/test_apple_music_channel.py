"""Apple Music канал обложек: чистые контракты без сети.

- developer token — валидный ES256 JWT: kid в заголовке, iss=Team ID,
  живёт ~12ч и кэшируется (второй вызов не перевыпускает);
- upc_variants даёт обе формы кода (EAN-13 ↔ UPC-A) без дублей — прививка
  от инцидента 18.08.2026 (Deezer + ведущий ноль, 1775 промахов подряд);
- artwork_from_payload подставляет размеры в шаблон {w}x{h} и не апскейлит
  выше родного размера артворка;
- configured() гейтит канал: без любого из трёх полей — выключен, и
  scheduled-джоба выходит до любых обращений к сети/БД.
"""
import base64
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services import apple_music  # noqa: E402


def _settings(monkeypatch, **env):
    monkeypatch.setenv("DEBUG", "true")
    for key in ("APPLE_MUSIC_TEAM_ID", "APPLE_MUSIC_KEY_ID", "APPLE_MUSIC_PRIVATE_KEY_B64"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    monkeypatch.setattr(apple_music, "get_settings", lambda: settings)
    return settings


@pytest.fixture(autouse=True)
def _reset_token_cache(monkeypatch):
    monkeypatch.setattr(apple_music, "_token_cache", None)


def _ec_key_b64() -> str:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode()


def test_configured_requires_all_three(monkeypatch):
    _settings(monkeypatch)
    assert apple_music.configured() is False
    _settings(monkeypatch, APPLE_MUSIC_TEAM_ID="T", APPLE_MUSIC_KEY_ID="K")
    assert apple_music.configured() is False
    _settings(monkeypatch, APPLE_MUSIC_TEAM_ID="T", APPLE_MUSIC_KEY_ID="K",
              APPLE_MUSIC_PRIVATE_KEY_B64="x")
    assert apple_music.configured() is True


def test_developer_token_shape_and_cache(monkeypatch):
    import jwt as pyjwt
    _settings(monkeypatch, APPLE_MUSIC_TEAM_ID="G47JLHB869",
              APPLE_MUSIC_KEY_ID="ABC123DEFG",
              APPLE_MUSIC_PRIVATE_KEY_B64=_ec_key_b64())
    token = apple_music._developer_token()
    header = pyjwt.get_unverified_header(token)
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert header["alg"] == "ES256"
    assert header["kid"] == "ABC123DEFG"
    assert claims["iss"] == "G47JLHB869"
    assert claims["exp"] - claims["iat"] == 12 * 3600
    # кэш: повторный вызов возвращает тот же токен без перевыпуска
    assert apple_music._developer_token() is token


def test_upc_variants_cover_leading_zero_incident():
    assert apple_music.upc_variants("0602547428813") == [
        "0602547428813", "602547428813",
    ]
    assert apple_music.upc_variants("602547428813") == [
        "602547428813", "0602547428813",
    ]
    # 13 без нуля и прочие длины — одна форма, без выдумок
    assert apple_music.upc_variants("5099902988313") == ["5099902988313"]
    assert apple_music.upc_variants("12345678") == ["12345678"]


def test_artwork_template_substitution():
    payload = {"data": [{"attributes": {"artwork": {
        "url": "https://is1-ssl.mzstatic.com/image/thumb/x/{w}x{h}bb.jpg",
        "width": 3000, "height": 3000,
    }}}]}
    url = apple_music.artwork_from_payload(payload)
    assert url == "https://is1-ssl.mzstatic.com/image/thumb/x/1200x1200bb.jpg"


def test_artwork_no_upscale_beyond_native():
    payload = {"data": [{"attributes": {"artwork": {
        "url": "https://x/{w}x{h}bb.jpg", "width": 600, "height": 600,
    }}}]}
    assert apple_music.artwork_from_payload(payload) == "https://x/600x600bb.jpg"


def test_artwork_missing_is_none():
    assert apple_music.artwork_from_payload({"data": []}) is None
    assert apple_music.artwork_from_payload({}) is None
    assert apple_music.artwork_from_payload({"data": [{"attributes": {}}]}) is None


def test_scheduled_batch_gated_on_config():
    """Без ключа scheduled-джоба обязана выйти ДО обращения к БД/сети."""
    from app.scripts import backfill_covers_apple as mod
    src = inspect.getsource(mod.run_scheduled_batch)
    assert "configured()" in src
    assert src.find("configured()") < src.find("_ensure_infra")


def test_worklist_targets_only_uncovered():
    """Очередь строится из строк без обложки — fill-NULL инвариант канала."""
    from app.scripts import backfill_covers_apple as mod
    src = inspect.getsource(mod._build_worklist)
    assert "cover_image_url IS NULL" in src
    src_persist = inspect.getsource(mod._persist)
    assert "AND cover_image_url IS NULL" in src_persist  # не перезаписываем
