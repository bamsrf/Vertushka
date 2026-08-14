"""Анти-SSRF: проверка внешних URL перед серверной закачкой.

Задача — не пустить наш собственный HTTP-клиент внутрь периметра. Внутри
docker-сети без всякой авторизации досягаемы `redis:6379`, `imgproxy:8080`,
`postgres:5432`; у хостера — link-local с метаданными (169.254.169.254).
Любое место, где сервер идёт по URL из БД или из чужого HTML, — это дверь туда.

Почему проверяем IP, а не список доменов. Обложки приезжают с Discogs, Deezer,
iTunes, Cover Art Archive, Yandex — и с CDN каждого магазина из таблицы
`stores`. Последние появляются вместе с новым парсером, то есть статический
allow-list пришлось бы дописывать руками при каждом добавлении магазина, и
однажды его забудут. Проверка «резолвится ли хост в публичный адрес» не требует
сопровождения и при этом закрывает ровно тот класс целей, который нам опасен.

Ограничение, о котором стоит знать: между нашим резолвом и коннектом httpx
теоретически влезает DNS rebinding (второй ответ DNS с приватным адресом).
Закрывается только пиннингом IP в транспорте; для закачки картинок это
избыточно, а вот при появлении эндпоинта, который ходит по URL пользователя и
ВОЗВРАЩАЕТ ему тело ответа, — придётся доделать.
"""
import asyncio
import ipaddress
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 5
# Потолок на тело ответа. Обложка в оригинале — сотни КБ; 20 МБ это уже
# «нам подсовывают что-то другое», и качать это в память незачем.
_MAX_BYTES = 20 * 1024 * 1024


class UnsafeUrlError(ValueError):
    """URL ведёт внутрь периметра либо синтаксически непригоден."""


def _ip_is_public(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return not (
        ip.is_private        # 10/8, 172.16/12, 192.168/16, fc00::/7 — docker-сеть тоже здесь
        or ip.is_loopback    # 127/8, ::1
        or ip.is_link_local  # 169.254/16 — метаданные облака
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def assert_safe_url(url: str) -> None:
    """Бросает UnsafeUrlError, если по URL нельзя ходить с сервера."""
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise UnsafeUrlError(f"не разбирается как URL: {exc}") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"схема {parsed.scheme!r} запрещена (только http/https)")

    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("в URL нет хоста")

    # Креды в URL — признак того, что ссылку собрали не мы. Заодно не хотим
    # утащить их в лог.
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL с учётными данными не принимаем")

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except Exception as exc:
        raise UnsafeUrlError(f"хост {host!r} не резолвится: {exc}") from exc

    if not infos:
        raise UnsafeUrlError(f"хост {host!r} не резолвится")

    # ВСЕ адреса должны быть публичными: хост с одной публичной и одной
    # приватной A-записью — классический обход проверки «хотя бы один».
    for info in infos:
        addr = info[4][0]
        if not _ip_is_public(addr):
            raise UnsafeUrlError(f"хост {host!r} резолвится в непубличный адрес {addr}")


async def safe_image_get(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET картинки с проверкой каждого хопа редиректа.

    httpx с follow_redirects=True проверку на входе обесценивает: разрешённый
    хост отвечает 302 на http://redis:6379 и клиент послушно идёт туда. Поэтому
    редиректы разматываем сами, валидируя каждый Location.
    """
    current = url
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS):
            await assert_safe_url(current)
            resp = await client.get(current, headers=headers)

            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise UnsafeUrlError("редирект без Location")
                # Относительный Location — достраиваем от текущего URL.
                current = str(httpx.URL(current).join(location))
                continue

            # Ранний отказ по заявленной длине, до чтения тела.
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > _MAX_BYTES:
                raise UnsafeUrlError(f"ответ {declared} байт — больше потолка {_MAX_BYTES}")
            if len(resp.content) > _MAX_BYTES:
                raise UnsafeUrlError(f"ответ {len(resp.content)} байт — больше потолка {_MAX_BYTES}")
            return resp

    raise UnsafeUrlError(f"больше {_MAX_REDIRECTS} редиректов подряд")


def is_safe_redirect_target(url: str | None) -> bool:
    """Синхронная проверка для 302, которые мы отдаём КЛИЕНТУ.

    Без резолва DNS: тут задача не в защите сервера, а в том, чтобы наш домен не
    работал открытым редиректором на произвольный хост. Хватает схемы и того,
    что хост — не литеральный внутренний адрес.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False
    host = parsed.hostname
    if not host or parsed.username or parsed.password:
        return False
    # Хост задан literal-адресом — пропускаем только публичный.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True  # обычное доменное имя
    return _ip_is_public(host)
