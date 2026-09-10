"""Страница-хаб /links и короткая ссылка /get.

Заменяет собой Linktree: те же ссылки, но на своём домене. Защищаем здесь не
вёрстку, а три вещи, которые ломаются молча:

1. Порядок блоков. /links — единственная страница, ссылку на которую можно
   давать из приложения, и ревьюер App Store её откроет. Платёжная форма выше
   сгиба читается как обход IAP (3.1.1). Поэтому донат на этой странице ведёт
   на /support, а не в CloudTips, и стоит после блока установки.
2. Гашение пустых блоков. Android ещё не вышел — кнопки сторов не должны
   рисоваться «вхолостую» с href="".
3. Совпадение data-goal в шаблоне и слушателя в _metrika.html — на этом уже
   обжигались с целью support_teaser (см. test_support_page.py).
"""
import re
from pathlib import Path

import pytest

PAY_HOST = "pay.cloudtips.ru"


@pytest.fixture(scope="module")
def jinja_env():
    from fastapi.templating import Jinja2Templates

    return Jinja2Templates(directory="app/web/templates").env


@pytest.fixture
def client():
    """Роутер без БД: /links и /get к ней не ходят."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.web import routes

    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


@pytest.fixture
def ctx():
    return {
        "request": None,
        "base_url": "https://vinyl-vertushka.ru",
        "app_store_url": "https://apps.apple.com/ru/app/test/id6774999020",
        "play_store_url": "",
        "rustore_url": "",
        "telegram_url": "https://t.me/slushnyaknow",
        "support_url": "/support",
        "support_plans_url": "https://timestripe.com/boards/test/",
        "metrika_id": "",
    }


class TestRoutes:
    def test_routes_registered(self):
        from app.main import app

        gets = {
            r.path for r in app.routes
            if getattr(r, "methods", None) and "GET" in r.methods
        }
        assert "/links" in gets
        assert "/get" in gets

    def test_page_survives_without_support_url(self, client, monkeypatch):
        """В отличие от /support, хаб осмыслен и с выключенными сборами.

        404 здесь был бы хуже всего: ссылку печатают на визитках и в шапке
        канала, а выключение донатов — обычная операция через переменную.
        """
        from app.web import routes

        monkeypatch.setattr(routes.settings, "support_url", "")
        resp = client.get("/links")
        assert resp.status_code == 200
        assert "Поддержать проект" not in resp.text

    @pytest.mark.parametrize("alias", ["APP_STORE_URL", "PLAY_STORE_URL"])
    def test_store_urls_not_duplicated_in_settings(self, alias):
        """Адрес каждой карточки в сторе — один на весь проект.

        Он же уходит мобилке как цель force-update и в CTA публичного профиля.
        Отдельное поле «ссылка для /links» означало бы две правды и почти
        наверняка разъехавшиеся значения — этот дубль уже заводили дважды.
        """
        source = Path("app/config.py").read_text(encoding="utf-8")
        assert source.count(f'alias="{alias}"') == 1


class TestSmartRedirect:
    """/get — то, что печатается на визитке. Ошибка здесь стоит установок."""

    @pytest.mark.parametrize("ua", [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
        "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)",
    ])
    def test_ios_goes_straight_to_app_store(self, client, ua):
        from app.config import get_settings

        resp = client.get("/get", headers={"user-agent": ua}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == get_settings().app_store_url

    @pytest.mark.parametrize("ua", [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/126",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126",
        "",
    ])
    def test_desktop_and_unknown_land_on_hub(self, client, ua):
        resp = client.get("/get", headers={"user-agent": ua}, follow_redirects=False)
        assert resp.headers["location"] == "/links"

    ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/126"

    def test_android_falls_back_to_hub_until_play_is_published(self, client):
        """PLAY_STORE_URL заполнен боевым адресом ЗАДОЛГО до публикации.

        Он нужен мобилке как цель force-update, поэтому пустым его не держат.
        Значит гейт — только PLAY_STORE_PUBLISHED; без него андроидовод уехал
        бы в 404 Google Play молча и без единой строки в логах.
        """
        from app.config import get_settings

        assert get_settings().play_store_published is False, (
            "приложение опубликовано в Play — тест пора переписать на обратный случай"
        )
        resp = client.get(
            "/get", headers={"user-agent": self.ANDROID_UA}, follow_redirects=False,
        )
        assert resp.headers["location"] == "/links"

    def test_android_uses_rustore_when_play_is_gated(self, client, monkeypatch):
        """RuStore не под флагом Play: появился адрес — можно вести туда."""
        from app.web import routes

        monkeypatch.setattr(routes.settings, "play_store_published", False)
        monkeypatch.setattr(routes.settings, "rustore_url", "https://apps.rustore.ru/app/x")
        resp = client.get(
            "/get", headers={"user-agent": self.ANDROID_UA}, follow_redirects=False,
        )
        assert resp.headers["location"] == "https://apps.rustore.ru/app/x"

    def test_android_goes_to_play_once_published(self, client, monkeypatch):
        from app.web import routes

        monkeypatch.setattr(routes.settings, "play_store_published", True)
        resp = client.get(
            "/get", headers={"user-agent": self.ANDROID_UA}, follow_redirects=False,
        )
        assert resp.headers["location"] == routes.settings.play_store_url

    def test_bots_get_the_page_not_a_redirect(self, client):
        """Краулеру и превьюшке мессенджера нужна OG-разметка, а не 302."""
        resp = client.get(
            "/get",
            headers={"user-agent": "TelegramBot (like TwitterBot)"},
            follow_redirects=False,
        )
        assert resp.headers["location"] == "/links"


class TestPage:
    def test_renders_all_configured_links(self, jinja_env, ctx):
        html = jinja_env.get_template("links.html").render(**ctx)
        assert ctx["app_store_url"] in html
        assert ctx["telegram_url"] in html
        assert ctx["support_plans_url"] in html

    def test_page_hides_play_button_until_published(self):
        """Шаблон гасит кнопку по пустой строке — гейт живёт в роуте."""
        import inspect

        from app.web import routes

        source = inspect.getsource(routes.links_page)
        assert "play_store_published" in source

    def test_empty_store_urls_render_no_buttons(self, jinja_env, ctx):
        html = jinja_env.get_template("links.html").render(**ctx)
        assert "Google Play" not in html
        assert "RuStore" not in html
        assert 'href=""' not in html

    def test_android_buttons_appear_when_configured(self, jinja_env, ctx):
        html = jinja_env.get_template("links.html").render(**{
            **ctx,
            "play_store_url": "https://play.google.com/store/apps/details?id=ru.vertushka",
            "rustore_url": "https://apps.rustore.ru/app/ru.vertushka",
        })
        assert "Google Play" in html
        assert "RuStore" in html

    def test_donation_goes_through_support_page(self, jinja_env, ctx):
        """3.1.1: ссылку на /links мы даём в том числе из приложения.

        Платёжный хост на этой странице означал бы прямой путь «кнопка в
        приложении → форма оплаты», который ревьюер и ищет.
        """
        html = jinja_env.get_template("links.html").render(**ctx)
        assert 'href="/support"' in html
        assert PAY_HOST not in html
        assert "cloudtips" not in html.lower()

    def test_block_order(self, jinja_env, ctx):
        """Порядок задан явно: установка, поддержка, канал, планы.

        Поддержка стоит второй сознательно. Прежняя редакция уводила её под
        сгиб ради оговорки 3.1.1 (платёжный CTA на первом экране страницы,
        открытой из приложения). Компенсация теперь другая и живёт вне этого
        файла: ссылку на /links НЕ дают из iOS-приложения — только канал, QR
        и визитка, а туда правило Apple не дотягивается. Появится ссылка из
        приложения — карточку поддержки надо вернуть вниз.
        """
        import re

        html = jinja_env.get_template("links.html").render(**ctx)
        assert re.findall(r'data-goal="(links_\w+)"', html) == [
            "links_appstore", "links_support", "links_telegram", "links_plans",
        ]

    def test_download_stays_the_primary_action(self, jinja_env, ctx):
        """Что бы ни стояло вторым, установка остаётся первой и единственной
        кнопкой: поддержка — карточка в общем списке, не второй CTA."""
        html = jinja_env.get_template("links.html").render(**ctx)
        assert html.index(ctx["app_store_url"]) < html.index('href="/support"')
        assert html.count("store-btn") > html.count('class="link-card warm"')

    def test_hub_survives_disabled_donations(self, jinja_env, ctx):
        html = jinja_env.get_template("links.html").render(**{**ctx, "support_url": ""})
        assert "Поддержать проект" not in html
        assert ctx["app_store_url"] in html
        assert ctx["telegram_url"] in html

    def test_promises_nothing_for_supporting(self, jinja_env, ctx):
        """Встречное предоставление превращает дар в доход — как и на /support."""
        html = jinja_env.get_template("links.html").render(**ctx).lower()
        for forbidden in ("взамен", "эксклюзив", "ранний доступ", "подписк"):
            assert forbidden not in html


class TestMetrikaGoals:
    """Цели воронки: сломанный селектор даёт честные нули, и это незаметно."""

    def test_every_link_goal_is_picked_up_by_the_listener(self, jinja_env, ctx):
        html = jinja_env.get_template("links.html").render(**{
            **ctx,
            "play_store_url": "https://play.google.com/store/apps/details?id=ru.vertushka",
            "rustore_url": "https://apps.rustore.ru/app/ru.vertushka",
        })
        metrika = Path("app/web/templates/_metrika.html").read_text(encoding="utf-8")

        assert re.search(r'closest\("\[data-goal\]"\)', metrika), (
            "в _metrika.html нет делегированного слушателя по data-goal"
        )

        goals = set(re.findall(r'data-goal="([\w-]+)"', html))
        assert goals == {
            "links_appstore", "links_googleplay", "links_rustore",
            "links_telegram", "links_plans", "links_support",
        }


class TestMotion:
    """Анимации крутятся сами — значит, отключение по запросу обязательно."""

    @pytest.fixture(scope="class")
    def css(self):
        return Path("app/web/templates/links.html").read_text(encoding="utf-8")

    def test_glint_runs_on_its_own_not_on_hover(self, css):
        """Блик по :hover на телефоне не показался бы никому.

        Ховера на тач-экране нет, а /links открывают в основном с телефона —
        главная кнопка страницы так и осталась бы статичной.
        """
        assert "links-glint" in css
        assert "infinite" in css.split("links-glint")[1][:200]
        assert ":hover::after { animation: links-glint" not in css

    def test_heart_pulses_on_the_icon_not_the_plate(self, css):
        """Масштабируй мы плашку — дёргалась бы подложка и строка заголовка."""
        assert ".link-card.warm .link-icon svg { animation: links-heartbeat" in css

    @pytest.mark.parametrize("selector", [
        ".store-btn:not(.secondary)::after { animation: none; }",
        ".link-card.warm .link-icon svg { animation: none; }",
    ])
    def test_reduced_motion_stops_both(self, css, selector):
        block = css.split("@media (prefers-reduced-motion: reduce)")[1]
        assert selector in block.split("}\n        }")[0] + "}\n        }"

    def test_no_leftover_divider(self, css):
        """Заголовок секции убран — поддержка живёт в общем списке карточек."""
        assert "Проекту можно помочь" not in css
        assert 'class="divider"' not in css
