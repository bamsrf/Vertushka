"""
Сервис получения курса валют от ЦБ РФ
"""
import time
import httpx

CBR_API_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
FALLBACK_USD_RUB = 90.0
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 часов

_cached_rate: float | None = None
_cached_at: float = 0.0


async def get_usd_rub_rate() -> float:
    """Получение курса USD/RUB от ЦБ РФ с кешированием"""
    global _cached_rate, _cached_at

    if _cached_rate and (time.time() - _cached_at) < CACHE_TTL_SECONDS:
        return _cached_rate

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(CBR_API_URL)
            response.raise_for_status()
            data = response.json()
            rate = data["Valute"]["USD"]["Value"]
            _cached_rate = float(rate)
            _cached_at = time.time()
            return _cached_rate
    except Exception:
        if _cached_rate:
            return _cached_rate
        return FALLBACK_USD_RUB
