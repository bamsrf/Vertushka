"""Фоновая задача не должна уносить с собой request_id запроса.

`asyncio.create_task` копирует contextvars, поэтому fire-and-forget задача
продолжает писать логи под идентификатором запроса, который её породил, — ещё
десятки секунд после того, как ответ ушёл. В логах это неотличимо от запроса,
висевшего минуту.

10.09.2026 на этом сгорел час разбора аларма про p99: «самые медленные
запросы» оказались прогревом обложек, а настоящие запросы отвечали за секунду.
Тесты ниже держат границу, чтобы это не вернулось.
"""
import asyncio

import pytest

from app.request_context import request_id_ctx, spawn_detached


@pytest.mark.asyncio
async def test_background_task_does_not_inherit_request_id():
    request_id_ctx.set("11112222-3333-4444-5555-666677778888")
    seen: list[str] = []

    async def work() -> None:
        seen.append(request_id_ctx.get())

    task = spawn_detached(work(), label="cover-warm")
    await task

    assert seen == ["bg:cover-warm:11112222"], (
        "фоновая задача обязана иметь собственный маркер, иначе её логи "
        "выглядят как зависший запрос"
    )


@pytest.mark.asyncio
async def test_marker_keeps_link_to_parent_request():
    """Связь с родителем не теряем — иначе фон нельзя сопоставить с запросом."""
    request_id_ctx.set("deadbeef-0000-1111-2222-333344445555")
    seen: list[str] = []

    async def work() -> None:
        seen.append(request_id_ctx.get())

    await spawn_detached(work(), label="enrich")

    assert seen[0].startswith("bg:enrich:")
    assert "deadbeef" in seen[0]


@pytest.mark.asyncio
async def test_works_without_parent_request():
    """Шедулер и стартап зовут то же самое вне HTTP-запроса."""
    request_id_ctx.set("-")
    seen: list[str] = []

    async def work() -> None:
        seen.append(request_id_ctx.get())

    await spawn_detached(work(), label="scheduler")

    assert seen == ["bg:scheduler"]


@pytest.mark.asyncio
async def test_caller_context_is_untouched():
    """Пометка живёт в задаче и не протекает обратно в запрос."""
    request_id_ctx.set("aaaabbbb-cccc-dddd-eeee-ffff00001111")

    await spawn_detached(asyncio.sleep(0), label="whatever")

    assert request_id_ctx.get() == "aaaabbbb-cccc-dddd-eeee-ffff00001111"


@pytest.mark.asyncio
async def test_task_is_retained_until_done():
    """Без сильной ссылки GC вправе забрать задачу — работа молча пропадёт."""
    done = asyncio.Event()

    async def work() -> None:
        await asyncio.sleep(0)
        done.set()

    spawn_detached(work(), label="retain")  # ссылку намеренно не держим
    await asyncio.wait_for(done.wait(), timeout=1.0)


def test_no_event_loop_is_survivable():
    """Вне async-контекста фон не имеет права ронять вызывающего."""
    async def work() -> None:
        pass

    coro = work()
    assert spawn_detached(coro, label="offline") is None
