"""Эффективный порог радара: абсолютный или «дешевле обычного».

Порог читается в трёх местах (GET /wishlists/radar и оба продюсера уведомлений —
in_stock и price_drop). Пока он был одним числом, дублирование было безобидным;
с появлением относительного режима разъехавшиеся формулы означали бы, что экран
показывает «подходит», а пуш не приходит. Поэтому расчёт живёт здесь один раз.

Режимы:
    threshold_pct задан  → порог = база × (1 − pct/100), база пересчитывается;
    иначе                → порог = price_threshold_rub (как было).

База — медиана дневных минимумов за BASELINE_DAYS. Медиана, а не среднее:
единственный демпинговый лот не должен обрушивать «обычную» цену. Дневной
минимум, а не все снапшоты: это ровно та величина, которую рисует график в
шторке цены, и обещание «дешевле обычного» должно совпадать с картинкой.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta
from statistics import median
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

# Окно базы. Совпадает с дефолтом графика в шторке цены (days=90).
BASELINE_DAYS = 90

# Минимум дней с данными, иначе базе нельзя верить: на двух точках «обычная
# цена» — это просто последняя цена, и относительный порог сработает мусорно.
MIN_BASELINE_DAYS = 5


# С какого момента журнал цен полон. Таблица listing_price_history заведена
# 14.07.2026 (миграция 20260713): с этого дня _upsert_listing пишет точку на
# каждую смену цены или статуса. Значит, у листинга, по которому с тех пор нет
# ни одной точки, цена и наличие не менялись — это доказуемо, а не догадка.
HISTORY_EPOCH = datetime(2026, 7, 14)


# Дневной минимум цены по записи — цена как СТУПЕНЬКА, а не как набор точек.
#
# Журнал пишет точку только при СМЕНЕ цены или статуса. Раньше и база радара,
# и график в шторке брали лишь дни, в которые была точка, — то есть дни
# изменений. У пластинки, которая месяц стоит 4 990 и никуда не двигается,
# такой день один (или ноль, если листинг старше журнала), база «меньше пяти
# дней» не отдавалась, и режим «дешевле обычного» молча падал на абсолютный
# порог — у кого рубли не заданы, на «слать всегда». Замер 19.09 по проду:
# база была у 32 пластинок из 320 в выборке по восьми магазинам; у Коробки
# Винила 28 из 40 не имели за 90 дней ни одной точки.
#
# Теперь каждая точка держит цену до следующей точки того же листинга, а
# последняя — до последнего наблюдения листинга (last_seen_at): обход бампает
# его раз в сутки, пока позиция жива, и перестаёт, когда она пропала. Листинг
# без единой точки даёт ступеньку текущей цены от HISTORY_EPOCH (или появления,
# если позже) до последнего наблюдения.
#
# Отрезки режутся по окну [since, now] и раскладываются по календарным дням;
# минимум дня — минимум по всем листингам записи, которые в этот день были
# в наличии.
_DAILY_MIN_SQL = text(
    """
    WITH pts AS (
        SELECT sl.matched_record_id AS record_id,
               h.listing_id,
               h.status,
               h.price_rub,
               h.captured_at AS start_at,
               COALESCE(
                   LEAD(h.captured_at) OVER (
                       PARTITION BY h.listing_id ORDER BY h.captured_at, h.id
                   ),
                   sl.last_seen_at
               ) AS end_at
        FROM listing_price_history h
        JOIN store_listings sl ON sl.id = h.listing_id
        WHERE sl.matched_record_id = ANY(:record_ids)
        UNION ALL
        SELECT sl.matched_record_id,
               sl.id,
               sl.status,
               sl.price_rub,
               GREATEST(sl.first_seen_at, :history_epoch),
               sl.last_seen_at
        FROM store_listings sl
        WHERE sl.matched_record_id = ANY(:record_ids)
          AND NOT EXISTS (
              SELECT 1 FROM listing_price_history h2 WHERE h2.listing_id = sl.id
          )
    ),
    spans AS (
        SELECT record_id,
               listing_id,
               price_rub,
               GREATEST(start_at, :since) AS span_start,
               LEAST(end_at, :now) AS span_end
        FROM pts
        WHERE status = 'in_stock'
          AND price_rub IS NOT NULL
    )
    SELECT record_id,
           d AS day,
           MIN(price_rub) AS min_price,
           COUNT(DISTINCT listing_id) AS listings
    FROM spans
    CROSS JOIN LATERAL generate_series(
        date_trunc('day', span_start),
        date_trunc('day', span_end),
        interval '1 day'
    ) AS d
    WHERE span_end >= span_start
    GROUP BY record_id, d
    ORDER BY record_id, d
    """
).bindparams(bindparam("record_ids", type_=ARRAY(PG_UUID(as_uuid=True))))


async def daily_min_prices(
    db: AsyncSession, record_ids: list[UUID], days: int
) -> list[tuple[UUID, datetime, Decimal, int]]:
    """[(record_id, день, минимум цены, листингов в наличии)] за `days` дней.

    Одна формула на базу радара и на график в шторке цены: обещание «дешевле
    обычного» обязано совпадать с картинкой, которую видит человек.
    """
    if not record_ids:
        return []
    now = datetime.utcnow()
    rows = await db.execute(
        _DAILY_MIN_SQL,
        {
            "record_ids": list(record_ids),
            "since": now - timedelta(days=days),
            "now": now,
            "history_epoch": HISTORY_EPOCH,
        },
    )
    return list(rows.all())


async def baseline_prices(
    db: AsyncSession, record_ids: list[UUID]
) -> dict[UUID, float]:
    """{record_id: медиана дневных минимумов за 90 дней} для записей с данными.

    Записи, у которых меньше MIN_BASELINE_DAYS дней в наличии, в ответ не
    попадают. Дни считаются по ступенчатой цене (см. _DAILY_MIN_SQL), то есть
    это дни, когда пластинка реально продавалась, а не дни, когда менялась цена.

    Привязка берётся джойном через store_listings.matched_record_id, а не из
    денормализованного listing_price_history.record_id: денорм пишется в
    _upsert_listing на момент снапшота, а матчинг идёт отдельной часовой
    задачей и историю не досыпает — до-матчевые строки лежат с record_id=NULL.
    """
    by_record: dict[UUID, list[float]] = {}
    for record_id, _day, min_price, _listings in await daily_min_prices(
        db, record_ids, BASELINE_DAYS
    ):
        if min_price is not None:
            by_record.setdefault(record_id, []).append(float(min_price))

    return {
        record_id: median(prices)
        for record_id, prices in by_record.items()
        if len(prices) >= MIN_BASELINE_DAYS
    }


def effective_threshold(
    price_threshold_rub: Decimal | float | None,
    threshold_pct: int | None,
    baseline: float | None,
) -> float | None:
    """Порог в рублях для сравнения с ценой лота. None = «уведомлять всегда».

    Относительный режим без базы (нет истории по записи) осознанно падает на
    абсолютный порог, а не молчит: пользователь подписался на пластинку, и
    отсутствие статистики не повод переставать за ней следить.
    """
    if threshold_pct is not None and baseline is not None:
        if threshold_pct <= 0 or threshold_pct >= 100:
            return None
        return round(baseline * (1 - threshold_pct / 100), 2)
    if price_threshold_rub is None:
        return None
    return float(price_threshold_rub)
