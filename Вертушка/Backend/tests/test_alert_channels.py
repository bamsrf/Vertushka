"""GlitchTip-webhook и почтовый мост — два новых источника Telegram-алармов.

Живой БД тесты не требуют (см. conftest): webhook проверяем на самом
эндпоинте с подменённой доставкой, IMAP — на разборе готового письма.

См. docs/plans/quality/TELEGRAM_ALERTS_PLAN.md
"""
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from app.api import internal
from app.services import alerts
from app.tasks import mailbox_tasks


class _Resp:
    status_code = 200
    text = ""


class _Client:
    """Подменяет httpx.AsyncClient, копя отправленные payload'ы в список."""

    def __init__(self, sink):
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json):
        self._sink.append(json)
        return _Resp()


@pytest.fixture
def sent(monkeypatch):
    box: list[dict] = []
    monkeypatch.setattr(alerts, "_enabled", lambda: True)
    monkeypatch.setattr(alerts.httpx, "AsyncClient", lambda **kw: _Client(box))
    return box


# ── GlitchTip ────────────────────────────────────────────────────────────


def test_extract_reads_slack_shaped_payload():
    title, body = internal._extract(
        {
            "attachments": [
                {
                    "title": "TypeError: NoneType",
                    "text": "в app/api/records.py",
                    "fields": [{"title": "Project", "value": "vertushka"}],
                    "title_link": "https://sentry.vinyl-vertushka.ru/issues/7",
                }
            ]
        }
    )
    assert title == "TypeError: NoneType"
    assert "app/api/records.py" in body
    assert "Project: vertushka" in body
    assert "issues/7" in body


def test_extract_survives_unknown_shape():
    """Формат payload у GlitchTip недокументирован и менялся между
    версиями. Молчащий аларм хуже кривого — сообщение должно уйти."""
    title, body = internal._extract({"text": "что-то стряслось"})
    assert title == "что-то стряслось"
    assert body == ""


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        internal, "get_settings",
        lambda: type("S", (), {"glitchtip_webhook_secret": "right"})(),
    )
    with pytest.raises(HTTPException) as exc:
        await internal.glitchtip_webhook("wrong", _request({}))
    # 404, а не 403: чужому сканеру незачем знать, что ручка существует.
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_webhook_answers_200_on_garbage(monkeypatch, sent):
    """GlitchTip на ошибку ретраит, а после серии ошибок отключает webhook —
    канал умрёт молча. Поэтому мусор глотаем с 200."""
    monkeypatch.setattr(
        internal, "get_settings",
        lambda: type("S", (), {"glitchtip_webhook_secret": "s"})(),
    )

    class _Broken:
        async def json(self):
            raise ValueError("not json")

    assert await internal.glitchtip_webhook("s", _Broken()) == {"ok": True}
    assert sent == []


@pytest.mark.asyncio
async def test_webhook_delivers_crash(monkeypatch, sent):
    monkeypatch.setattr(
        internal, "get_settings",
        lambda: type("S", (), {"glitchtip_webhook_secret": "s"})(),
    )
    monkeypatch.setattr(alerts, "_should_send", lambda key: (True, 0))

    await internal.glitchtip_webhook(
        "s", _request({"attachments": [{"title": "Boom", "text": "трейс"}]})
    )

    assert len(sent) == 1
    assert sent[0]["text"].startswith("💥 <b>Boom</b>")


def _request(payload):
    class _Req:
        async def json(self):
            return payload

    return _Req()


# ── Почта ────────────────────────────────────────────────────────────────


def test_decodes_mime_headers():
    """Тема письма от реального человека почти всегда в =?utf-8?B?…?=."""
    assert mailbox_tasks._decode("=?utf-8?B?0J/RgNC40LLQtdGC?=") == "Привет"


def test_decode_survives_broken_header():
    assert mailbox_tasks._decode("=?bogus?X?zzz?=") == "=?bogus?X?zzz?="


def _multipart(*parts: tuple[str, str]) -> email.message.Message:
    """Собрать письмо как его собирает почтовик: base64 поверх utf-8.

    Разбирать письмо, слепленное из голых строк, бессмысленно — в IMAP
    таких не бывает, а get_payload(decode=True) на них врёт.
    """
    outer = MIMEMultipart("alternative")
    for subtype, text in parts:
        outer.attach(MIMEText(text, subtype, "utf-8"))
    return email.message_from_bytes(outer.as_bytes())


def test_plain_text_prefers_text_part():
    message = _multipart(("html", "<p>разметка</p>"), ("plain", "чистый текст"))
    assert mailbox_tasks._plain_text(message).strip() == "чистый текст"


def test_plain_text_falls_back_to_html():
    """Письма из веб-морд бывают только в HTML — лучше разметка, чем пустота."""
    message = _multipart(("html", "<p>разметка</p>"))
    assert "разметка" in mailbox_tasks._plain_text(message)


def test_plain_text_reads_simple_letter():
    """Не-multipart письмо — самый частый случай для support@."""
    message = email.message_from_bytes(MIMEText("одна часть", "plain", "utf-8").as_bytes())
    assert mailbox_tasks._plain_text(message).strip() == "одна часть"


@pytest.mark.asyncio
async def test_poll_is_noop_without_credentials(monkeypatch):
    """Локальная разработка не должна ломиться в боевой ящик."""
    called = False

    def _boom():
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(mailbox_tasks, "_fetch_unseen", _boom)
    monkeypatch.setattr(
        mailbox_tasks, "get_settings",
        lambda: type("S", (), {"mailbox_imap_user": "", "mailbox_imap_password": ""})(),
    )
    await mailbox_tasks.poll_support_mailbox()
    assert called is False


@pytest.mark.asyncio
async def test_poll_marks_seen_only_after_send(monkeypatch, sent):
    """Порядок принципиален: пометили раньше отправки — потеряли письмо
    навсегда, если Telegram не ответил."""
    order: list[str] = []

    monkeypatch.setattr(
        mailbox_tasks, "get_settings",
        lambda: type("S", (), {"mailbox_imap_user": "u", "mailbox_imap_password": "p"})(),
    )
    monkeypatch.setattr(
        mailbox_tasks, "_fetch_unseen",
        lambda: [(b"1", "user@example.com", "Не грузится", "тело")],
    )
    monkeypatch.setattr(mailbox_tasks, "_mark_seen", lambda uid: order.append("seen"))

    original = alerts.send_notice

    async def _tracked(*args, **kwargs):
        order.append("sent")
        await original(*args, **kwargs)

    monkeypatch.setattr(alerts, "send_notice", _tracked)

    await mailbox_tasks.poll_support_mailbox()

    assert order == ["sent", "seen"]
    assert "Не грузится" in sent[0]["text"]
    assert "user@example.com" in sent[0]["text"]


@pytest.mark.asyncio
async def test_mail_bypasses_throttle(monkeypatch, sent):
    """Троттлинг схлопнул бы пять писем в «+4 таких же», потеряв ровно то,
    ради чего канал заводили."""
    monkeypatch.setattr(
        mailbox_tasks, "get_settings",
        lambda: type("S", (), {"mailbox_imap_user": "u", "mailbox_imap_password": "p"})(),
    )
    monkeypatch.setattr(
        mailbox_tasks, "_fetch_unseen",
        lambda: [(bytes(str(i), "ascii"), "a@b.c", f"Тема {i}", "тело") for i in range(5)],
    )
    monkeypatch.setattr(mailbox_tasks, "_mark_seen", lambda uid: None)

    await mailbox_tasks.poll_support_mailbox()

    assert len(sent) == 5


@pytest.mark.asyncio
async def test_imap_failure_alerts_once(monkeypatch, sent):
    """Недоступный IMAP — новость, но с троттлингом: сеть у Beget моргает."""
    monkeypatch.setattr(
        mailbox_tasks, "get_settings",
        lambda: type("S", (), {"mailbox_imap_user": "u", "mailbox_imap_password": "p"})(),
    )

    def _explode():
        raise OSError("connection refused")

    monkeypatch.setattr(mailbox_tasks, "_fetch_unseen", _explode)
    monkeypatch.setattr(alerts, "_should_send", lambda key: (True, 0))

    await mailbox_tasks.poll_support_mailbox()

    assert len(sent) == 1
    assert "Ящик поддержки недоступен" in sent[0]["text"]
