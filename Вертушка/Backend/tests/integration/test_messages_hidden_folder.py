"""Папка «Скрытые»: скрытый диалог достижим и возвращается обратно.

До этого «Скрыть диалог» ставил archived_at, а GET /conversations/ его молча
фильтровал — папки не было, и вернуть тред можно было только наткнувшись на
профиль собеседника. Проверяем контракт папки целиком:

- скрытый уходит из primary и появляется в archived;
- просмотр треда архивацию НЕ снимает (иначе в папку нельзя заглянуть);
- unarchive возвращает в ту папку, откуда пришло: отклонённый запрос — в
  requests, обычный диалог — в primary.
"""
import uuid

import pytest

from app.models.user import User

pytestmark = pytest.mark.asyncio


@pytest.fixture
def partner(db):
    async def _make() -> User:
        user = User(
            email=f"partner-{uuid.uuid4().hex[:8]}@example.com",
            username=f"partner{uuid.uuid4().hex[:8]}",
            password_hash="x",
            display_name="Собеседник",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    return _make


async def _folder(client, name: str) -> list[str]:
    r = await client.get("/messages/conversations/", params={"folder": name})
    assert r.status_code == 200, r.text
    return [c["id"] for c in r.json()]


async def test_hidden_conversation_is_reachable_and_restorable(client, partner):
    other = await partner()

    r = await client.post(
        "/messages/conversations/", json={"recipient_user_id": str(other.id)}
    )
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]
    assert conv_id in await _folder(client, "primary")

    # Скрываем
    r = await client.delete(f"/messages/conversations/{conv_id}/")
    assert r.status_code == 200
    assert conv_id not in await _folder(client, "primary")
    assert conv_id in await _folder(client, "archived")

    # Заглянуть в тред можно, не возвращая его в список
    r = await client.get(f"/messages/conversations/{conv_id}/")
    assert r.status_code == 200
    assert conv_id in await _folder(client, "archived")
    assert conv_id not in await _folder(client, "primary")

    # Возврат — явным действием, и идемпотентно
    for _ in range(2):
        r = await client.post(f"/messages/conversations/{conv_id}/unarchive/")
        assert r.status_code == 200
    assert conv_id in await _folder(client, "primary")
    assert conv_id not in await _folder(client, "archived")


async def test_rejected_request_lands_in_archive_and_returns_as_request(
    client, partner, as_user, owner
):
    """Отклонённый запрос — тоже «скрытое», и возвращается запросом, а не в Личные."""
    other = await partner()

    as_user(other)
    r = await client.post(
        "/messages/conversations/", json={"recipient_user_id": str(owner.id)}
    )
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]

    as_user(owner)
    assert conv_id in await _folder(client, "requests")

    r = await client.post(f"/messages/conversations/{conv_id}/reject/")
    assert r.status_code == 200
    assert conv_id not in await _folder(client, "requests")
    assert conv_id in await _folder(client, "archived")

    r = await client.post(f"/messages/conversations/{conv_id}/unarchive/")
    assert r.status_code == 200
    assert conv_id in await _folder(client, "requests")
    assert conv_id not in await _folder(client, "primary")
