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
from app.services.cover_quality import MASTER_MIN_SIDE

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

        # Тир зеркалированных мастеров. Это детектор той самой поломки: пока
        # `_thumb_to_cover` молча возвращала 150px-thumb, доля мелких доросла до
        # 54% (13 124 из 24 404), и увидели мы это случайно, глазами, через
        # недели. `unmeasured` — файлы до появления cover_min_side; их размер
        # проставляет scripts/heal_cover_tiers, и в норме он стремится к нулю.
        tier_row = (await db.execute(text(
            "SELECT count(*) AS mirrored, "
            "count(*) FILTER (WHERE cover_min_side IS NULL) AS unmeasured, "
            "count(*) FILTER (WHERE cover_min_side IS NOT NULL "
            f"                  AND cover_min_side < {MASTER_MIN_SIDE}) AS low_res "
            "FROM records WHERE cover_local_path IS NOT NULL"
        ))).mappings().one()

        # Откуда пришли обложки. Считаем по хосту URL в дамп-индексе: отдельной
        # колонки source там нет, а хост однозначен. Цифра нужна для решения по
        # изоляции — выпиливать Discogs из лестницы мастеров можно только зная,
        # сколько релизов реально закрывают бесплатные источники.
        source_row = (await db.execute(text(
            "SELECT "
            "  count(*) FILTER (WHERE cover_image_url LIKE '%coverartarchive.org%') AS caa, "
            "  count(*) FILTER (WHERE cover_image_url LIKE '%dzcdn.net%') AS deezer, "
            "  count(*) FILTER (WHERE cover_image_url LIKE '%mzstatic.com%') AS itunes, "
            "  count(*) FILTER (WHERE cover_image_url LIKE '%discogs.com%') AS discogs, "
            "  count(*) FILTER (WHERE cover_image_url IS NOT NULL "
            "    AND cover_image_url NOT LIKE '%coverartarchive.org%' "
            "    AND cover_image_url NOT LIKE '%dzcdn.net%' "
            "    AND cover_image_url NOT LIKE '%mzstatic.com%' "
            "    AND cover_image_url NOT LIKE '%discogs.com%') AS other "
            "FROM discogs_releases_index"
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
    tier = {
        "mirrored": tier_row["mirrored"],
        "low_res": tier_row["low_res"],
        "unmeasured": tier_row["unmeasured"],
        "threshold_px": MASTER_MIN_SIDE,
        # Доля считается от ПРОМЕРЕННЫХ, а не от всех зеркал: иначе метрика
        # выглядела бы тем лучше, чем больше файлов мы ещё не измерили.
        "low_res_pct": _pct(tier_row["low_res"], tier_row["mirrored"] - tier_row["unmeasured"]),
    }
    sources = {k: source_row[k] for k in ("caa", "deezer", "itunes", "discogs", "other")}
    free = sources["caa"] + sources["deezer"] + sources["itunes"]
    sources["free_pct"] = _pct(free, free + sources["discogs"] + sources["other"])

    snapshot = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "dump_index": dump,
        "market_in_stock": market,
        "master_tier": tier,
        "cover_sources": sources,
    }

    await cache.set(_SNAPSHOT_NS, _SNAPSHOT_KEY, snapshot, ttl=_SNAPSHOT_TTL)
    logger.info(
        "cover coverage: dump_index %d/%d (%.1f%%), market_in_stock %d/%d (%.1f%%), "
        "low-res masters %d (%.1f%% of measured, %d unmeasured), free sources %.1f%%",
        dump["with_cover"], dump["total"], dump["pct"] * 100,
        market["with_cover"], market["total"], market["pct"] * 100,
        tier["low_res"], tier["low_res_pct"] * 100, tier["unmeasured"],
        sources["free_pct"] * 100,
    )

    _maybe_alert(market, prev)
    _maybe_alert_tier(tier, prev)
    return snapshot


def _maybe_alert_tier(tier: dict, prev: dict | None) -> None:
    """Алерт на РОСТ доли мелких мастеров — детектор повтора поломки тира.

    Именно рост, а не абсолютный уровень: накопленные 13 124 мелких обложек
    рассасываются ночным перегревом постепенно, и алертить на них каждый день
    значит выучиться игнорировать алерты. А вот если доля пошла ВВЕРХ — значит
    в зеркало снова течёт мелкое, и гейт где-то обойдён.
    """
    prev_tier = (prev or {}).get("master_tier") if prev else None
    if not prev_tier or not tier["low_res_pct"]:
        return
    growth_pp = (tier["low_res_pct"] - prev_tier.get("low_res_pct", 0)) * 100
    if growth_pp > 1.0:
        alerts.fire_and_forget(
            key="cover_tier_regression",
            title=f"Доля мелких мастеров обложек выросла на {growth_pp:.1f} п.п.",
            body=(
                f"Было {prev_tier.get('low_res_pct', 0) * 100:.1f}%, стало "
                f"{tier['low_res_pct'] * 100:.1f}% ({tier['low_res']} обложек "
                f"мельче {tier['threshold_px']}px). Рост означает, что гейт тира "
                f"обойдён — проверить cover_quality и источники в лестнице."
            ),
        )


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
