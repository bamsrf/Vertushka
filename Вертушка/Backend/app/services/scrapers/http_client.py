"""
HTTP-клиент для парсеров с per-domain rate-limit, circuit-breaker, прокси-пулом
и детектом Cloudflare-challenge.

Паттерн повторяет app/services/discogs.py — один shared httpx.AsyncClient на процесс.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from urllib.parse import urlparse

import httpx

from app.services.scrapers.robots import is_allowed
from app.services.scrapers.ua_pool import random_headers

logger = logging.getLogger(__name__)


# ---- Per-domain circuit breaker (вынесено из discogs.py) ---------------- #


class CircuitOpenError(Exception):
    """Circuit OPEN для домена."""


class _CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, reset_after_sec: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_after_sec = reset_after_sec
        self._state = self.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    async def before_request(self, label: str = "") -> None:
        async with self._lock:
            if self._state == self.OPEN:
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at >= self.reset_after_sec:
                    self._state = self.HALF_OPEN
                    logger.warning("[%s] circuit HALF_OPEN — probing", label)
                else:
                    raise CircuitOpenError(f"{label}: circuit OPEN")

    async def record_success(self, label: str = "") -> None:
        async with self._lock:
            if self._state != self.CLOSED:
                logger.info("[%s] circuit CLOSED — recovered", label)
            self._state = self.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None

    async def record_failure(self, label: str = "") -> None:
        async with self._lock:
            self._consecutive_failures += 1
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning("[%s] probe failed — circuit OPEN again", label)
            elif self._consecutive_failures >= self.failure_threshold:
                if self._state != self.OPEN:
                    logger.warning(
                        "[%s] circuit OPEN after %d failures",
                        label, self._consecutive_failures,
                    )
                self._state = self.OPEN
                self._opened_at = time.monotonic()


# ---- Per-domain token-bucket rate-limiter (упрощённая версия) ---------- #


class _DomainBucket:
    """Token-bucket без приоритетов — простой sleep-based лимитер per-domain."""

    def __init__(self, capacity: int = 2, refill_rate: float = 0.5):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._refill_rate
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now


# ---- Cloudflare-детектор ------------------------------------------------ #


_CF_MARKERS = (
    "__cf_chl",
    "cf-mitigated",
    "cf_chl_opt",
    "challenge-platform",
    "/cdn-cgi/challenge",
    "DDoS protection by Cloudflare",
    "Just a moment",
)


def _is_cf_challenge(resp: httpx.Response) -> bool:
    if resp.status_code in (403, 503):
        if resp.headers.get("server", "").lower().startswith("cloudflare"):
            body_lower = resp.text[:8192].lower()
            if any(m.lower() in body_lower for m in _CF_MARKERS):
                return True
        # DDoS-Guard:
        if "ddos-guard" in resp.headers.get("server", "").lower():
            return True
    return False


# ---- Главный клиент ----------------------------------------------------- #


def _parse_proxies(env: str | None) -> list[str]:
    if not env:
        return []
    return [p.strip() for p in env.split(",") if p.strip()]


class ScraperHttpClient:
    """Async HTTP-клиент для парсеров.

    - Один shared httpx.AsyncClient (лениво).
    - Per-domain bucket + circuit-breaker.
    - Опциональный прокси-пул через env SCRAPER_PROXIES (CSV "http://host:port,...").
    - Детект Cloudflare/DDoS-Guard → ParserNeedsBrowser.
    - 429/503 → backoff с уважением Retry-After.
    """

    _clients: dict[str | None, httpx.AsyncClient] = {}
    _proxies: list[str] = _parse_proxies(os.environ.get("SCRAPER_PROXIES"))

    def __init__(self) -> None:
        self._buckets: dict[str, _DomainBucket] = {}
        self._breakers: dict[str, _CircuitBreaker] = {}

    @classmethod
    def _get_client(cls, proxy: str | None) -> httpx.AsyncClient:
        """Per-proxy AsyncClient. proxy=None → прямое соединение."""
        client = cls._clients.get(proxy)
        if client is None or client.is_closed:
            kwargs: dict = {
                # 90 с на чтение: страницы листингов у магазинов тяжёлые
                # (doctorhead ~2 МБ, plastinka ~9 МБ), и при пяти параллельных
                # обходах 30 с не хватало — таймауты открывали брейкер.
                "timeout": httpx.Timeout(90.0, connect=10.0),
                "limits": httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,
                ),
                "follow_redirects": True,
                "http2": False,  # часть РФ-магазинов на старых nginx
            }
            if proxy:
                kwargs["proxy"] = proxy
            client = httpx.AsyncClient(**kwargs)
            cls._clients[proxy] = client
        return client

    @classmethod
    async def aclose(cls) -> None:
        for client in list(cls._clients.values()):
            if not client.is_closed:
                await client.aclose()
        cls._clients.clear()

    def configure_domain(self, domain: str, *, rate_per_sec: float, burst: int) -> None:
        """Задать per-domain rate-limit. Идемпотентно."""
        if domain not in self._buckets:
            self._buckets[domain] = _DomainBucket(capacity=burst, refill_rate=rate_per_sec)
        if domain not in self._breakers:
            self._breakers[domain] = _CircuitBreaker()

    async def get_text(
        self,
        url: str,
        *,
        respect_robots: bool = True,
        retries: int = 2,
    ) -> str:
        """GET → текст. Бросает ParserBlocked / ParserNeedsBrowser / TransientParserError."""
        # Импорт внутри: избегаем циклической зависимости с base.py
        from app.services.scrapers.base import (
            ParserBlocked,
            ParserNeedsBrowser,
            TransientParserError,
        )

        domain = urlparse(url).netloc
        bucket = self._buckets.get(domain) or _DomainBucket()
        breaker = self._breakers.get(domain) or _CircuitBreaker()
        # Регистрируем дефолтные если не было configure_domain
        self._buckets.setdefault(domain, bucket)
        self._breakers.setdefault(domain, breaker)

        proxy = random.choice(self._proxies) if self._proxies else None
        client = self._get_client(proxy)
        headers = random_headers()

        if respect_robots and not await is_allowed(client, url, headers["User-Agent"]):
            logger.info("robots.txt disallow %s", url)
            raise ParserBlocked(f"robots.txt disallow: {url}")

        try:
            await breaker.before_request(domain)
        except CircuitOpenError as e:
            raise TransientParserError(str(e))

        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            await bucket.acquire()
            try:
                resp = await client.get(url, headers=headers)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                last_exc = e
                # Брейкер считает ОДИН провал на URL, а не на попытку: иначе
                # два флакующих URL по 3 попытки выбирают порог в 5 и рвут
                # обход из сотни страниц (инцидент doctorhead 08-10).
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                await breaker.record_failure(domain)
                raise TransientParserError(f"network error: {e}") from e

            if resp.status_code == 200:
                if _is_cf_challenge(resp):
                    raise ParserNeedsBrowser(f"Cloudflare/DDoS-Guard challenge at {url}")
                await breaker.record_success(domain)
                return resp.text

            if resp.status_code in (429, 503):
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                wait = max(retry_after, 30 * (2 ** attempt))
                if attempt < retries:
                    await asyncio.sleep(min(wait, 300))
                    continue
                await breaker.record_failure(domain)
                raise TransientParserError(f"rate-limited {resp.status_code} at {url}")

            if resp.status_code in (403, 401):
                if _is_cf_challenge(resp):
                    raise ParserNeedsBrowser(f"Cloudflare challenge {resp.status_code} at {url}")
                raise ParserBlocked(f"HTTP {resp.status_code} at {url}")

            if resp.status_code in (404, 410):
                raise ParserError_404(url)  # not transient — товар удалён

            if 500 <= resp.status_code < 600:
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                await breaker.record_failure(domain)
                raise TransientParserError(f"HTTP {resp.status_code} at {url}")

            raise TransientParserError(f"HTTP {resp.status_code} at {url}")

        if last_exc:
            raise TransientParserError(str(last_exc)) from last_exc
        raise TransientParserError("unexpected loop exit")

    async def get_bytes(self, url: str, *, respect_robots: bool = False) -> bytes:
        """GET → bytes (для sitemap.xml/yml.xml — gzip хендлится httpx сам)."""
        from app.services.scrapers.base import (
            ParserBlocked,
            TransientParserError,
        )

        proxy = random.choice(self._proxies) if self._proxies else None
        client = self._get_client(proxy)
        headers = random_headers()
        if respect_robots and not await is_allowed(client, url, headers["User-Agent"]):
            raise ParserBlocked(f"robots.txt disallow: {url}")
        try:
            resp = await client.get(url, headers=headers)
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            raise TransientParserError(f"network error: {e}") from e
        if resp.status_code != 200:
            raise TransientParserError(f"HTTP {resp.status_code} at {url}")
        return resp.content


def _parse_retry_after(value: str | None) -> float:
    if not value:
        return 60.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 60.0


class ParserError_404(Exception):
    """Товар удалён (404/410). Не transient — пометить status='removed'."""

    def __init__(self, url: str):
        super().__init__(f"404 at {url}")
        self.url = url


# Singleton
http_client = ScraperHttpClient()
