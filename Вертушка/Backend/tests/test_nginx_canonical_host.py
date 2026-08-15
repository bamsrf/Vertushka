"""Каждое имя, ведущее на наш IP, обязано иметь свой 443-блок.

Инцидент 2026-08-15: люди жаловались, что раздел поддержки «небезопасный».
Дело было не в сертификате апекса — он валиден. Дело в том, что www вообще
не был описан на 443, и TLS-хендшейк попадал в первый по порядку 443-server
(money.vinyl-vertushka.ru) как в default_server. Браузер получал сертификат
на чужое имя и предупреждал.

Редирект на 80 порту от этого не спасает: человек, у которого в адресе уже
https://, до 80-го порта не доходит вовсе. Имя должно быть либо в SAN
сертификата и в своём server-блоке, либо не резолвиться в наш IP совсем.
"""
import re
from pathlib import Path

import pytest

CONF = Path("nginx/nginx.conf").read_text(encoding="utf-8")


def server_blocks() -> list[str]:
    """Тела server{...} верхнего уровня внутри http{}."""
    blocks = []
    for m in re.finditer(r"^\s{4}server\s*\{", CONF, re.M):
        i, depth, body = m.end(), 1, []
        while i < len(CONF) and depth:
            ch = CONF[i]
            depth += ch == "{"
            depth -= ch == "}"
            if depth:
                body.append(ch)
            i += 1
        blocks.append("".join(body))
    return blocks


def block_for(host: str, port: str) -> str | None:
    for b in server_blocks():
        names = re.search(r"server_name\s+([^;]+);", b)
        listens = re.findall(r"listen\s+([^;]+);", b)
        if not names or not any(port in l for l in listens):
            continue
        if host in names.group(1).split():
            return b
    return None


class TestWww:
    def test_www_has_its_own_tls_block(self):
        """Без него www уезжает в default_server с чужим сертификатом."""
        assert block_for("www.vinyl-vertushka.ru", "443") is not None

    def test_www_redirects_to_apex(self):
        """Канонический адрес один: иначе две версии сайта в выдаче и
        расхождение OG-ссылок при шеринге профилей."""
        block = block_for("www.vinyl-vertushka.ru", "443")
        assert re.search(
            r"return\s+301\s+https://vinyl-vertushka\.ru\$request_uri;", block
        )

    def test_www_uses_the_apex_certificate(self):
        """Отдельного сертификата у www нет — апексный выписан на оба имени
        через --expand. Если тут появится свой путь, продлевать придётся два,
        и один тихо протухнет."""
        block = block_for("www.vinyl-vertushka.ru", "443")
        assert "/etc/letsencrypt/live/vinyl-vertushka.ru/fullchain.pem" in block

    def test_www_still_answers_acme_on_port_80(self):
        """Продление ходит по HTTP. Если www выпадет из 80-го блока,
        --expand перестанет проходить, и на 90-й день отвалится уже всё."""
        block = block_for("www.vinyl-vertushka.ru", "80")
        assert block is not None
        assert "/.well-known/acme-challenge/" in block


class TestApex:
    def test_apex_serves_content_not_redirect(self):
        block = block_for("vinyl-vertushka.ru", "443")
        assert block is not None
        assert not re.search(r"^\s*return\s+301", block, re.M), (
            "апекс — канонический хост, он не должен никуда редиректить"
        )

    @pytest.mark.parametrize("host", ["vinyl-vertushka.ru", "www.vinyl-vertushka.ru"])
    def test_hsts_on_both_names(self, host):
        assert "Strict-Transport-Security" in block_for(host, "443")
