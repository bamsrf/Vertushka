"""Метрика покрытия обложек — закрывает п.4.2 MARKET_COVERS_AND_INGEST_FIX.

Раньше цифру покрытия снимали руками по SSH (`psql ... COUNT`). Эта задача
считает её на расписании, кладёт снапшот в Redis (читается без SSH через
`/health/covers`), пишет в лог и шлёт Telegram-алерт при регрессии.

Две метрики — разные вопросы, обе нужны:

  1. **dump_index** — доля каталога `discogs_releases_index`, для которой мы
     ЗНАЕМ URL обложки (не факт, что зеркалирована). Это прогресс прогрева.
  2. **market_in_stock** — доля in_stock matched-листингов с РАБОЧЕЙ обложкой
     (то, что реально видит юзер в маркете). Считается тем же выражением
     `_COVER_EXPR_LISTING`, которым маркет рендерит карточку, — иначе метрика
     разъедется с реальностью. Это метрика §4.2 и главный сигнал качества.

Алерт: по market_in_stock. Срабатывает при падении ниже абсолютного пола
(COVER_COVERAGE_MIN_RATIO) ИЛИ при просадке относительно прошлого снапшота
больше чем на COVER_COVERAGE_ALERT_DROP_PP пунктов. Относительная просадка
не зависит от того, какой у нас базовый уровень — ловит именно регресс.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.services import alerts
from app.services.cache import cache

logger = logging.getLogger(__name__)

_SNAPSHOT_NS = "metrics"
_SNAPSHOT_KEY = "cover_coverage"
# Снапшот живёт дольше суточного интервала задачи — читатель всегда видит
# последнюю цифру, даже если один прогон пропущен.
_SNAPSHOT_TTL = 8 * 86400


def _pct(with_cover: int, total: int) -> float:
    """Доля 0..1, деление на ноль → 0.0."""
    return round(with_cover / total, 4) if total else 0.0


async def report_cover_coverage() -> dict:
    """Посчитать покрытие обложек, сохранить снапшот, при регрессии — алерт.

    Возвращает снапшот (для тестов/ручного вызова). Все ошибки логируются,
    наружу не пробрасываются — задача в scheduler не должна ронять цикл.
    """
    # Выражение «рабочая обложка» — единый источник истины с витриной маркета.
    # Ленивый импорт: market.py тяжёлый, тянем только в момент прогона.
    from app.api.market import _COVER_EXPR_LISTING

    prev = await cache.get(_SNAPSHOT_NS, _SNAPSHOT_KEY)

    async with async_session_maker() as db:
        dump_row = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE cover_image_url IS NOT NULL) AS with_cover, "
            "count(*) AS total FROM discogs_releases_index"
        ))).mappings().one()

        market_row = (await db.execute(text(
            f"SELECT count(*) AS total, "
            f"count(*) FILTER (WHERE {_COVER_EXPR_LISTING} IS NOT NULL) AS with_cover "
            f"FROM store_listings sl "
            f"JOIN records r ON r.id = sl.matched_record_id "
            f"WHERE sl.status = 'in_stock'"
        ))).mappings().one()

    dump = {
        "with_cover": dump_row["with_cover"],
        "total": dump_row["total"],
        "pct": _pct(dump_row["with_cover"], dump_row["total"]),
    }
    market = {
        "with_cover": market_row["with_cover"],
        "total": market_row["total"],
        "pct": _pct(market_row["with_cover"], market_row["total"]),
    }
    snapshot = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "dump_index": dump,
        "market_in_stock": market,
    }

    await cache.set(_SNAPSHOT_NS, _SNAPSHOT_KEY, snapshot, ttl=_SNAPSHOT_TTL)
    logger.info(
        "cover coverage: dump_index %d/%d (%.1f%%), market_in_stock %d/%d (%.1f%%)",
        dump["with_cover"], dump["total"], dump["pct"] * 100,
        market["with_cover"], market["total"], market["pct"] * 100,
    )

    _maybe_alert(market, prev)
    return snapshot


def _maybe_alert(market: dict, prev: dict | None) -> None:
    """Алерт по market_in_stock: абсолютный пол ИЛИ регресс к прошлому снапшоту."""
    settings = get_settings()
    # Пустой маркет (total=0) — не повод для алерта: обложек нет, потому что
    # товара нет, а не потому что что-то сломалось.
    if market["total"] == 0:
        return

    floor = settings.cover_coverage_min_ratio
    drop_pp = settings.cover_coverage_alert_drop_pp
    cur = market["pct"]

    if cur < floor:
        alerts.fire_and_forget(
            key="cover_coverage_floor",
            title=f"Обложки маркета: покрытие {cur * 100:.1f}% ниже пола {floor * 100:.0f}%",
            body=(
                f"in_stock matched с рабочей обложкой: "
                f"{market['with_cover']}/{market['total']}. "
                f"Проверить enrichment-джобы и источники обложек."
            ),
        )
        return

    prev_market = (prev or {}).get("market_in_stock") if prev else None
    if prev_market and prev_market.get("total"):
        delta_pp = (prev_market["pct"] - cur) * 100
        if delta_pp > drop_pp:
            alerts.fire_and_forget(
                key="cover_coverage_regression",
                title=f"Обложки маркета просели на {delta_pp:.1f} п.п. за сутки",
                body=(
                    f"Было {prev_market['pct'] * 100:.1f}%, стало {cur * 100:.1f}% "
                    f"({market['with_cover']}/{market['total']}). "
                    f"Порог просадки: {drop_pp:.0f} п.п."
                ),
            )
