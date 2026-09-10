"""Корень домена: человеку — /links, машине — JSON статуса.

vinyl-vertushka.ru/ отдавал голый JSON `{"app": ..., "status": "running"}` —
человеку, набравшему домен руками, это выглядит как сломанный сайт.

Развилка сделана по заголовку Accept, а не по User-Agent, и это главное, что
тут защищается: браузер всегда просит text/html, а curl, healthcheck'и и
мониторинг шлют `*/*`. Перепутать легко, а сломанный мониторинг обнаруживается
ровно тогда, когда он был нужен.

Healthcheck'и docker-compose и внешняя проверка deploy.sh стучатся в /health,
а не в корень, — но JSON тут оставлен намеренно, как страховка.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestBrowser:
    # Реальные заголовки: Chrome/Safari, Firefox и краулер Telegram.
    BROWSER_ACCEPTS = [
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "text/html",
    ]

    @pytest.mark.parametrize("accept", BROWSER_ACCEPTS)
    def test_browser_goes_to_the_hub(self, client, accept):
        resp = client.get("/", headers={"accept": accept}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/links"

    def test_redirect_actually_lands_on_a_page(self, client):
        """Ссылка назначения должна существовать — редирект в 404 хуже JSON."""
        resp = client.get("/", headers={"accept": "text/html"}, follow_redirects=True)
        assert resp.status_code == 200
        assert "Вертушка" in resp.text


class TestMachines:
    """Всё, что не просит HTML, обязано получить прежний ответ без изменений."""

    MACHINE_ACCEPTS = [
        "*/*",              # curl, wget, httpx по умолчанию
        "application/json",
        "",                 # заголовка нет вовсе
    ]

    @pytest.mark.parametrize("accept", MACHINE_ACCEPTS)
    def test_status_json_is_unchanged(self, client, accept):
        resp = client.get("/", headers={"accept": accept}, follow_redirects=False)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert set(body) == {"app", "version", "status", "docs"}

    def test_health_endpoint_untouched(self, client):
        """На /health завязаны healthcheck контейнера и гейт деплоя.

        Код не фиксируем: без живой БД /health честно отдаёт 503, и это его
        работа. Важно ровно одно — что он не стал редиректом: healthcheck
        docker-compose ходит без follow и посчитал бы 302 провалом.
        """
        resp = client.get("/health", follow_redirects=False)
        assert resp.status_code in (200, 503)
        assert "location" not in resp.headers

    def test_split_is_by_accept_not_user_agent(self):
        """User-Agent тут не при чём — и не должен появиться.

        Проверка по UA означала бы список браузеров, который устаревает молча:
        новый клиент попадал бы не в свою ветку, и никто бы не заметил.
        """
        import ast
        import inspect

        from app.main import root

        # Разбираем в AST и выкидываем докстринг: комментарии ast.unparse не
        # переносит, так что остаётся чистый код. Иначе тест ловил бы слово
        # «User-Agent» из собственного объяснения в докстринге функции —
        # ровно на этом он и упал в первый прогон.
        fn = ast.parse(inspect.getsource(root)).body[0]
        if (
            fn.body
            and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)
        ):
            fn.body = fn.body[1:]
        code = ast.unparse(fn).lower()

        assert "accept" in code
        assert "user-agent" not in code
        assert "user_agent" not in code
