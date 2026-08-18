"""Стоимость коллекции показывается всегда — тумблера больше нет.

Настройка была лишним шагом: профиль публикуется осознанно, а стоимость по
умолчанию стояла false, поэтому у большинства опубликованных профилей
hero-карточка была пустой. Теперь решение одно — «публиковать или нет».

Тест держит инвариант с трёх сторон: схема не принимает выключение, модель
рождает новые профили с true, а публичные места не спрашивают флаг.
"""
import inspect
from pathlib import Path

from app.models.profile_share import ProfileShare
from app.schemas.profile import ProfileShareSettings, ProfileShareUpdate

BACKEND = Path(__file__).resolve().parents[1]


def test_update_schema_cannot_disable_value():
    """Старый клиент пришлёт show_collection_value=false — поле игнорируется."""
    assert "show_collection_value" not in ProfileShareUpdate.model_fields

    parsed = ProfileShareUpdate(show_collection_value=False)
    assert not hasattr(parsed, "show_collection_value")
    assert parsed.model_dump(exclude_unset=True) == {}


def test_response_schema_defaults_to_shown():
    """Поле остаётся в ответе ради старых сборок мобилки — и всегда true."""
    assert ProfileShareSettings.model_fields["show_collection_value"].default is True


def test_new_profiles_are_created_with_value_shown():
    column = ProfileShare.__table__.c.show_collection_value
    assert column.default.arg is True
    assert "true" in str(column.server_default.arg).lower()


def test_public_surfaces_do_not_gate_on_the_flag():
    """Ни расчёт, ни рендер не должны спрашивать флаг — иначе он снова оживёт."""
    from app.api import profile as profile_api
    from app.web import routes as web_routes

    for module in (profile_api, web_routes):
        src = inspect.getsource(module)
        assert "if profile.show_collection_value" not in src, module.__name__

    template = (
        BACKEND / "app" / "web" / "templates" / "public_profile.html"
    ).read_text(encoding="utf-8")
    assert "profile.show_collection_value" not in template
