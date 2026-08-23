"""Страница разбора жалоб.

До неё единственным способом закрыть жалобу был curl со staff-токеном, а
обещанная в Условиях реакция ≤24ч держалась на готовности владельца ночью
открыть терминал. Страница — тонкий каркас поверх /api/reports; вся защита
осталась на require_staff, поэтому тесты стерегут именно то, что легко
сломать правкой шаблона: origin запросов, экранирование UGC и noindex.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

TEMPLATE = Path("app/web/templates/admin_reports.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    return TestClient(app)  # без `with` — lifespan намеренно не запускаем


def test_page_is_served(client):
    res = client.get("/admin/reports")

    assert res.status_code == 200
    assert "Жалобы" in res.text


def test_page_is_not_indexable(client):
    """Ссылка на модераторку в выдаче — приглашение перебирать пароли."""
    res = client.get("/admin/reports")

    assert "noindex" in res.headers.get("X-Robots-Tag", "")
    assert 'name="robots"' in res.text


def test_requests_stay_same_origin():
    """CORS пускает только основной домен: абсолютный хост в fetch убил бы
    страницу на api-хосте молча, на preflight."""
    assert "var API = '/api';" in TEMPLATE
    assert "https://api.vinyl-vertushka.ru" not in TEMPLATE


def test_ugc_never_reaches_innerhtml():
    """Превью и причина приходят от тех, на кого жалуются: любая запись в
    innerHTML отдаёт им исполнение скрипта в сессии модератора."""
    assert not re.search(r"\.innerHTML\s*(=|\+=)", TEMPLATE)
    assert "textContent" in TEMPLATE


def test_ban_is_confirmed_and_labelled_irreversible():
    """Разбана эндпоинтом нет — только UPDATE в БД. Промах мышью не должен
    стоить пользователю аккаунта."""
    assert "window.confirm" in TEMPLATE
    assert "необратим" in TEMPLATE


def test_offered_actions_match_the_api_contract():
    """Кнопка, которой нет в ReportAction, вернёт 422 уже после клика."""
    from app.schemas.report import ReportAction
    from typing import get_args

    allowed = set(get_args(ReportAction))
    offered = set(re.findall(r"action: '([a-z_]+)'", TEMPLATE))
    assert offered
    assert offered <= allowed, offered - allowed


def test_hide_record_not_offered_for_user_reports():
    """hide_record применим только к жалобам на записи — на жалобе о юзере
    он вернёт 400, и staff решит, что интерфейс сломан."""
    block = TEMPLATE[TEMPLATE.index("user: ["):]
    block = block[: block.index("]")]
    assert "hide_record" not in block
    assert "ban_user" in block
