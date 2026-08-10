"""Трекинг переходов в магазин: UTM, псевдоним юзера, детект ботов.

Почему на это нужны тесты: все три функции ломаются молча. Неверная UTM-метка
не бросает исключение — переход просто становится невидимым в аналитике
магазина, и узнаём мы об этом через месяц, когда цифры не сойдутся с их GA.

См. docs/plans/CLICK_REDIRECTOR_AND_METRIKA.md
"""
from urllib.parse import parse_qs, urlparse

from app.services.affiliate import _add_utm, _user_tag
from app.utils.bot_ua import is_bot_ua

UID = "11111111-2222-3333-4444-555555555555"


def _qs(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


class TestAddUtm:
    def test_adds_our_utm_to_clean_url(self):
        qs = _qs(_add_utm("https://shop.ru/item/1"))
        assert qs["utm_source"] == "vertushka"
        assert qs["utm_medium"] == "mobile"
        assert qs["utm_campaign"] == "offers"

    def test_overrides_foreign_utm(self):
        """Главный регресс-кейс: раньше стоял setdefault и чужая метка выживала.

        Каталожные ссылки из JSON-LD и фидов приносят свой utm_source. Если его
        не перетереть, магазин увидит трафик как «yandex/cpc», а не как наш, и
        переход выпадет из отчётов, которыми мы обосновываем партнёрку.
        """
        qs = _qs(_add_utm("https://shop.ru/item/1?utm_source=yandex&utm_medium=cpc"))
        assert qs["utm_source"] == "vertushka"
        assert qs["utm_medium"] == "mobile"

    def test_preserves_non_utm_params(self):
        """Товарные параметры трогать нельзя — иначе ссылка ведёт не туда."""
        qs = _qs(_add_utm("https://shop.ru/item?id=7&variant=blue&utm_campaign=summer"))
        assert qs["id"] == "7"
        assert qs["variant"] == "blue"
        assert qs["utm_campaign"] == "offers"

    def test_keeps_path_and_host(self):
        url = _add_utm("https://shop.ru/lp/item/357894-some-slug")
        assert url.startswith("https://shop.ru/lp/item/357894-some-slug?")

    def test_malformed_url_does_not_raise(self):
        """Переход важнее метки: на кривом URL отдаём что есть, а не 500."""
        assert _add_utm("not-a-url") is not None


class TestUserTag:
    def test_raw_uuid_never_leaks(self):
        """utm_content уезжает на чужой домен — сырой users.id туда нельзя."""
        url = _add_utm("https://shop.ru/i", user_id=UID)
        assert UID not in url
        assert "11111111" not in url

    def test_deterministic(self):
        """Иначе магазин увидит одного человека как N разных посетителей."""
        assert _user_tag(UID) == _user_tag(UID)

    def test_different_users_differ(self):
        assert _user_tag(UID) != _user_tag("99999999-2222-3333-4444-555555555555")

    def test_lands_in_utm_content(self):
        assert _qs(_add_utm("https://shop.ru/i", user_id=UID))["utm_content"].startswith("u_")

    def test_anonymous_has_no_utm_content(self):
        assert "utm_content" not in _qs(_add_utm("https://shop.ru/i"))


class TestBotUa:
    def test_messenger_previews_are_bots(self):
        for ua in (
            "TelegramBot (like TwitterBot)",
            "WhatsApp/2.23",
            "facebookexternalhit/1.1",
            "Mozilla/5.0 (compatible; Googlebot/2.1)",
            "Slackbot-LinkExpanding 1.0",
        ):
            assert is_bot_ua(ua), ua

    def test_scripted_clients_are_bots(self):
        """Накрутка через curl/requests не должна попадать в отчёт магазину."""
        for ua in ("curl/8.4.0", "python-requests/2.31.0", "Go-http-client/1.1"):
            assert is_bot_ua(ua), ua

    def test_empty_ua_is_bot(self):
        assert is_bot_ua(None)
        assert is_bot_ua("")

    def test_real_browsers_are_not_bots(self):
        for ua in (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36",
        ):
            assert not is_bot_ua(ua), ua
