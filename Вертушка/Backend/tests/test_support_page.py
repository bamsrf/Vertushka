"""Раздел «Поддержать проект»: страница /support, блок и компактный вход.

Главное, что тут защищается, — не вёрстка, а правило App Store 3.1.1:
платёжная ссылка живёт только в вебе. Если она когда-нибудь просочится в
мобильное приложение, приложение поедет на отклонение — а узнаем мы об этом
через неделю ревью. Дешевле узнать здесь.

Живой БД и HTTP-клиент не нужны: шаблоны рендерим напрямую через Jinja,
маршрут проверяем по таблице роутов.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PAY_HOST = "pay.cloudtips.ru"


@pytest.fixture(scope="module")
def jinja_env():
    from fastapi.templating import Jinja2Templates

    return Jinja2Templates(directory="app/web/templates").env


@pytest.fixture
def ctx():
    return {
        "support_url": f"https://{PAY_HOST}/p/testlink",
        "support_plans_url": "https://timestripe.com/boards/test/",
        "base_url": "https://vinyl-vertushka.ru",
        "metrika_id": "",
        "request": None,
    }


class TestRoute:
    def test_support_route_registered(self):
        from app.main import app

        gets = {
            r.path for r in app.routes
            if getattr(r, "methods", None) and "GET" in r.methods
        }
        assert "/support" in gets

    def test_empty_support_url_gives_404(self):
        """Пустой SUPPORT_URL = сборы выключены без выкатки кода."""
        import inspect

        from app.web import routes

        source = inspect.getsource(routes.support_page)
        assert "settings.support_url" in source
        assert "404" in source or "HTTP_404_NOT_FOUND" in source


class TestBlock:
    def test_renders_payment_link_and_cta(self, jinja_env, ctx):
        html = jinja_env.get_template("_support.html").render(**ctx)
        assert ctx["support_url"] in html
        assert "Поддержать проект" in html

    def test_hidden_without_url(self, jinja_env, ctx):
        html = jinja_env.get_template("_support.html").render(**{**ctx, "support_url": ""})
        assert html.strip() == ""

    def test_says_payment_is_one_off(self, jinja_env, ctx):
        """«Разовый» снимает главный страх перед чужой платёжной формой.

        Заодно это ещё одна страховка от толкования платежа как подписки —
        а подписка означала бы и встречное предоставление, и IAP.
        """
        html = jinja_env.get_template("_support.html").render(**ctx)
        assert "разовый" in html.lower()

    def test_promises_nothing_in_return(self, jinja_env, ctx):
        """Встречное предоставление превращает дар в доход — §5–6 плана.

        Заодно это граница 3.2.1(vii): подарок, связанный с получением
        цифрового контента, обязан идти через IAP.
        """
        html = jinja_env.get_template("_support.html").render(**ctx)
        assert "бесплатное приложение и таким останется" in html
        for forbidden in ("взамен", "эксклюзив", "ранний доступ", "подписк"):
            assert forbidden not in html.lower()


class TestTeaser:
    def test_leads_to_support_page_not_to_payment(self, jinja_env, ctx):
        """В профиле ведём на /support, а не сразу на платёжку.

        Так человек по дороге читает, за что платит, и профиль не выглядит
        витриной сборов.
        """
        html = jinja_env.get_template("_support_teaser.html").render(**ctx)
        assert 'href="/support"' in html
        assert PAY_HOST not in html

    def test_metrika_selector_matches_pill_class(self, jinja_env, ctx):
        """Селектор цели должен совпадать с классом плашки.

        Прод-инцидент 2026-08-15: плашку переименовали из `.support-teaser` в
        `.support-pill`, а слушатель в _metrika.html остался на старом классе —
        цель `support_teaser` не сработала бы ни разу, и сломанной аналитике
        никто бы не удивился (нулей ждёшь и так).
        """
        html = jinja_env.get_template("_support_teaser.html").render(**ctx)
        metrika = Path("app/web/templates/_metrika.html").read_text(encoding="utf-8")

        selector = re.search(r'closest\("a\.(support-[\w-]+)"\)[^}]*?support_teaser', metrika, re.S)
        assert selector, "в _metrika.html нет слушателя цели support_teaser"
        assert f'class="{selector.group(1)}"' in html

    def test_uses_logo_not_mascot_frame(self, jinja_env, ctx):
        """В шапке плашка крошечная: кадр с бегущим маскотом там нечитаем."""
        html = jinja_env.get_template("_support_teaser.html").render(**ctx)
        assert "support-logo.png" in html
        assert "support-mascot" not in html

    def test_hidden_without_url(self, jinja_env, ctx):
        html = jinja_env.get_template("_support_teaser.html").render(**{**ctx, "support_url": ""})
        assert html.strip() == ""

    def test_profile_includes_teaser_not_full_block(self):
        tpl = (Path("app/web/templates/public_profile.html")).read_text(encoding="utf-8")
        assert '{% include "_support_teaser.html" %}' in tpl
        assert '{% include "_support.html" %}' not in tpl


class TestPage:
    def test_page_renders_with_block_and_faq(self, jinja_env, ctx):
        html = jinja_env.get_template("support.html").render(**ctx)
        assert ctx["support_url"] in html
        assert "Частые вопросы" in html
        assert ctx["support_plans_url"] in html

    def test_page_states_minimum_amount(self, jinja_env, ctx):
        """Нижняя граница CloudTips — 50 ₽.

        В блоке её больше нет (там про разовость), значит единственное место,
        где человек может о ней прочитать до перехода, — FAQ.
        """
        html = jinja_env.get_template("support.html").render(**ctx)
        assert "50 ₽" in html

    def test_page_has_no_app_cta(self, jinja_env, ctx):
        """На /support ровно одно целевое действие."""
        html = jinja_env.get_template("support.html").render(**ctx)
        assert "Попробовать приложение" not in html


class TestAppStoreGuard:
    """3.1.1: ни кнопок, ни ссылок на оплату мимо IAP внутри приложения."""

    @pytest.mark.parametrize("needle", [PAY_HOST, "cloudtips"])
    def test_payment_link_never_ships_in_mobile_app(self, needle):
        mobile = REPO_ROOT / "Mobile"
        if not mobile.exists():
            pytest.skip("Mobile/ нет в этом чекауте")

        skip_dirs = {"node_modules", ".expo", "dist", "ios", "android", "build"}
        hits = []
        for path in mobile.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".json"}:
                continue
            if skip_dirs & set(path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if needle in text.lower():
                hits.append(str(path.relative_to(REPO_ROOT)))

        assert not hits, (
            f"платёжная ссылка просочилась в мобильное приложение: {hits}. "
            "App Store Guideline 3.1.1 — во всех сторфронтах, кроме US, кнопки и "
            "внешние ссылки на оплату мимо IAP запрещены. "
            "См. docs/plans/product/PLAN_SUPPORT_PROJECT.md"
        )
