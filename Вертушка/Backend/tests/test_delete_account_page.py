"""Публичная страница удаления аккаунта — требование Google Play.

Google Play обязывает приложения с регистрацией давать ссылку на веб-страницу
с инструкцией по удалению (Data safety → Data deletion). Страница должна
открываться без логина и без поднятых Redis/БД: это статический документ,
и его недоступность — повод для отклонения на ревью.
"""
import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)  # без lifespan — Redis/БД не нужны


def test_delete_account_page_opens_without_auth(client):
    response = client.get("/delete-account")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_delete_account_page_has_required_content(client):
    """Шаги в приложении, сроки, контакт — минимум, который смотрит ревью Play."""
    html = client.get("/delete-account").text

    assert "Удалить аккаунт" in html, "шаги удаления в приложении"
    assert "30 дней" in html, "окно восстановления и срок окончательного удаления"
    assert "support@vinyl-vertushka.store" in html, "контакт для запроса удаления"
    assert "/privacy" in html
