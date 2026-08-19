"""Спрос на обложки: сколько холодных просмотров и сколько добычи в сутки.

Зачем. Планирование ёмкости упиралось в число, которого никто не знал: какая
доля просмотров обложек — холодные, то есть требуют похода к источникам. Прикидка
«примерно четверть» давала разброс выводов от «упрёмся через неделю» до
«запаса на год», а вытащить её из данных постфактум не выходит: прирост
`records.cover_cached_at` определяется фоновыми джобами (бэкфиллы, ночной
перегрев), а не людьми, и одно с другим в этой колонке не разделено.

Здесь две метрики, обе суточные:

1. **Холодные просмотры** — считаются в `GET /covers/{id}`. Этот эндпоинт зовёт
   nginx ТОЛЬКО когда мастера нет на диске (`try_files ... @covers_fallback`),
   поэтому каждый его вызов по определению холодный, и это живой пользовательский
   трафик, а не фон. Пишем и общее число обращений, и оценку уникальных релизов:
   разница между ними — это повторные показы, то есть эффективность кэша.

2. **Добыча по триггерам** — кто именно скачал обложку: пользовательское
   действие, ночной перегрев, бэкфилл или магазинный харвест. Без этого
   разделения рост зеркала невозможно отнести к нагрузке от людей.

Отношение «холодных уникальных в сутки / DAU» — то самое число, на которое
умножается прогноз. Всё остальное (диск, троттлы источников, лимиты Discogs)
считается из него арифметикой.

Метрики никогда не влияют на ответ пользователю: Redis недоступен — молча
пропускаем. Обложка важнее статистики.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from app.services.cache import cache

logger = logging.getLogger(__name__)

_NS = "cover_demand"
# 40 дней: хватает и на недельные срезы, и на сравнение «до/после» изменений,
# при этом ключи не копятся бесконечно.
_TTL = 40 * 86400

# Триггеры добычи. Строки попадают в имена ключей Redis, менять с оглядкой на
# уже накопленные данные.
TRIGGER_USER = "user"          # ensure_cover_cached — добавление в коллекцию/вишлист
TRIGGER_SWEEP = "sweep"        # ночной перегрев мелких мастеров
TRIGGER_BACKFILL = "backfill"  # скрипты и фоновые бэкфиллы
TRIGGER_STORE = "store"        # харвест магазинных листингов
_TRIGGERS = (TRIGGER_USER, TRIGGER_SWEEP, TRIGGER_BACKFILL, TRIGGER_STORE)

# Исходы холодного запроса GET /covers/{id}. Общее число холодных обращений
# (cold_hits) не отвечает на вопрос «что юзер увидел»: 302 на внешний CDN,
# заглушку после мгновенного 404 или заглушку после 6-секундной лестницы —
# это три разных продукта. Разбивка по исходам показывает, куда уходит холодный
# трафик и работает ли negative-cache/дедуп/бюджет.
OUTCOME_REDIRECT = "redirect"    # 302 из БД/индекса — URL уже был известен
OUTCOME_LIVE_HIT = "live_hit"    # живой резолв нашёл URL → 302
OUTCOME_LIVE_MISS = "live_miss"  # живой резолв провалился/таймаут → 404
OUTCOME_NEG_CACHE = "neg_cache"  # 404 из negative-кэша, лестница не ходила
OUTCOME_BUSY = "busy"            # 404: резолв этого id уже идёт или семафор полон
OUTCOME_BUDGET = "budget"        # 404: дневной бюджет Discogs-картинок исчерпан
OUTCOME_NOT_FOUND = "not_found"  # 404: ни записи, ни URL, ни пути к резолву
_OUTCOMES = (
    OUTCOME_REDIRECT, OUTCOME_LIVE_HIT, OUTCOME_LIVE_MISS,
    OUTCOME_NEG_CACHE, OUTCOME_BUSY, OUTCOME_BUDGET, OUTCOME_NOT_FOUND,
)


def _today() -> str:
    return date.today().isoformat()


async def record_cold_request(discogs_id: str) -> None:
    """Холодный просмотр: мастера на диске не было, запрос дошёл до бэкенда."""
    if not discogs_id:
        return
    day = _today()
    await cache.incr(_NS, f"cold_hits:{day}", ttl=_TTL)
    await cache.pfadd(_NS, f"cold_uniq:{day}", discogs_id, ttl=_TTL)


async def record_cold_outcome(outcome: str) -> None:
    """Чем закончился холодный запрос (см. OUTCOME_* выше)."""
    if outcome not in _OUTCOMES:
        return
    await cache.incr(_NS, f"cold_out:{_today()}:{outcome}", ttl=_TTL)


async def record_acquisition(trigger: str) -> None:
    """Обложка реально скачана и уложена на диск."""
    if trigger not in _TRIGGERS:
        trigger = TRIGGER_BACKFILL
    await cache.incr(_NS, f"acq:{_today()}:{trigger}", ttl=_TTL)


async def demand_snapshot(days: int = 7) -> dict:
    """Срез спроса за последние `days` суток (включая сегодняшние неполные).

    Возвращает по дню: холодные обращения, уникальные холодные релизы, добыча в
    разбивке по триггерам. DAU подмешивает вызывающий — здесь только обложки.
    """
    out: list[dict] = []
    today = date.today()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        acq = {}
        for t in _TRIGGERS:
            acq[t] = await cache.get_counter(_NS, f"acq:{d}:{t}") or 0
        outcomes = {}
        for o in _OUTCOMES:
            outcomes[o] = await cache.get_counter(_NS, f"cold_out:{d}:{o}") or 0
        out.append({
            "date": d,
            "cold_hits": await cache.get_counter(_NS, f"cold_hits:{d}") or 0,
            "cold_unique": await cache.pfcount(_NS, f"cold_uniq:{d}"),
            "cold_outcomes": outcomes,
            "acquired": acq,
        })
    return {"days": out}
