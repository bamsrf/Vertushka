"""
request_id: сам контекст запроса и правильный запуск фоновых задач.

Почему в одном модуле. `asyncio.create_task` копирует contextvars, поэтому
fire-and-forget задача уносит с собой request_id запроса, который её породил,
— и продолжает писать под ним логи ещё десятки секунд после того, как ответ
ушёл клиенту. В логах это выглядит как запрос, висевший минуту.

Так и получилось при разборе аларма на p99 10.09.2026: топ «самых медленных
запросов» целиком состоял из прогрева обложек (cover_warm), а настоящие
запросы отвечали за секунду. Час ушёл на погоню за аварией, которой не было.

Поэтому фоновую задачу запускаем через `spawn_detached`: она получает СВОЙ
маркер `bg:<что>:<8 символов родителя>`. Связь с породившим запросом
сохраняется — по префиксу его всё ещё видно, — но перепутать фон с запросом
больше нельзя.

Задачи, результат которых запрос ЖДЁТ (`asyncio.shield`, `wait_for`, `gather`),
через `spawn_detached` пускать не надо: это часть обработки запроса, и
request_id у них должен остаться родительским.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
from contextvars import ContextVar
from typing import Any, Coroutine

logger = logging.getLogger(__name__)

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# Держим ссылки на живые задачи: без этого GC вправе забрать таску до
# завершения, и работа молча пропадёт (см. asyncio docs, create_task).
_detached: set[asyncio.Task] = set()


def spawn_detached(
    coro: Coroutine[Any, Any, Any], *, label: str
) -> asyncio.Task | None:
    """Запустить фоновую задачу с собственным request_id.

    label — что это за работа («cover-warm», «enrich»): попадёт в логи и
    делает их читаемыми без раскопок по коду.

    Возвращает None, если нет живого event loop (вызов не из async-контекста)
    — как и alerts.fire_and_forget, фон не имеет права ронять вызывающего.
    """
    parent = request_id_ctx.get()
    marker = f"bg:{label}"
    if parent and parent != "-":
        marker = f"{marker}:{parent[:8]}"

    ctx = contextvars.copy_context()
    ctx.run(request_id_ctx.set, marker)

    try:
        task = asyncio.create_task(coro, context=ctx)
    except RuntimeError:
        coro.close()
        logger.warning("spawn_detached вне event loop, задача пропущена: %s", label)
        return None

    _detached.add(task)
    task.add_done_callback(_detached.discard)
    return task
