"""Контракт Android-канала пушей (WS3).

Канал `default` создаётся на клиенте (Mobile/lib/push.ts::ensureAndroidPushChannel),
а бэкенд обязан класть тот же channelId в каждое сообщение Expo Push API —
и в одиночные send_push, и в батчи, где сообщения собираются снаружи.
"""
import httpx

from app.services import push


def test_channel_id_is_default_and_matches_mobile_contract():
    assert push.ANDROID_PUSH_CHANNEL_ID == "default"


def test_with_android_channel_fills_missing_and_keeps_explicit():
    msgs = [
        {"to": "ExponentPushToken[a]", "title": "t", "body": "b"},
        {"to": "ExponentPushToken[b]", "title": "t", "body": "b", "channelId": "chat"},
    ]
    out = push.with_android_channel(msgs)
    assert out[0]["channelId"] == "default"
    assert out[1]["channelId"] == "chat"
    # Исходные dict'ы не мутируются
    assert "channelId" not in msgs[0]


async def test_post_with_retry_sends_channel_id(monkeypatch):
    sent: list = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"status": "ok", "id": "r1"}]}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.append(json)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    single = [{"to": "ExponentPushToken[x]", "title": "t", "body": "b"}]
    await push._post_with_retry(single)
    assert sent[-1]["channelId"] == "default"  # одиночный payload — dict

    batch = [
        {"to": "ExponentPushToken[x]", "title": "t", "body": "b"},
        {"to": "ExponentPushToken[y]", "title": "t", "body": "b"},
    ]
    await push._post_with_retry(batch)
    assert isinstance(sent[-1], list)
    assert all(m["channelId"] == "default" for m in sent[-1])
