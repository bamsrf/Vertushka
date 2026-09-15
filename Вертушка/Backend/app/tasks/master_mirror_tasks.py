"""Зеркалирование мастер-обложек из уже известных URL.

Зачем. Мастер закрывает в среднем 3.1 релиза (877 548 мастеров адресуют
2.7 млн позиций), а источники у мастеров на 98% бесплатные — CAA и Deezer.
На 15.09.2026 в бакете лежало 28 970 мастеров из 877 548 с известным URL, то
есть 3.3%: адреса бесплатные каналы собрали, а за байтами никто не сходил.
Пока байтов нет, холодный показ уходит редиректом на чужой хост — медленно,
зависит от их лимитов и ломается, когда подписанный URL протухает.

Чем это НЕ является: дрипом. Дрип спрашивает Discogs «а есть ли обложка», его
очередь — 10.5 млн строк при общем с юзерами лимите 60 rpm, то есть покрыть
дамп он не может в принципе. Здесь адрес уже известен, внешних API нет, есть
только скачивание с бесплатного CDN. Строки с source='discogs' пропускаем
намеренно — их картинки идут под дневной бюджет Discogs, который нужен живым
пользователям.

Темп ограничен с двух сторон:
  - MASTER_MIRROR_BATCH × pace внутри прогона — вежливость к чужому CDN;
  - MASTER_MIRROR_DAILY_CAP — дневной потолок. Он про ДЕНЬГИ: каждый файл
    оседает в бакете навсегда, 848 тыс. мастеров это ~85 ГБ. Потолок держит
    прирост предсказуемым (20 000 ≈ 2 ГБ/сутки), пока владелец не решит,
    сколько готов платить за хранение.

Очередь самоочищающаяся: `mirrored_at IS NULL AND mirror_attempts < LIMIT`.
Это прямой вывод из аварии дрипа 14.09 — там одна незакрывающаяся строка
держала голову очереди сутки, потому что счётчика попыток не было вовсе.
"""
import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import text

from app.config import get_settings
from app.database import async_session_maker
from app.services.cache import cache

logger = logging.getLogger(__name__)

# Больше — и строка уходит из очереди навсегда. Три попытки покрывают
# «CDN моргнул», но не дают мёртвому URL съедать прогон за прогоном.
_MAX_ATTEMPTS = 3
# Прогон обязан влезать в свой интервал: перерасход не падает, а молча роняет
# следующий тик (max_instances=1) — темп проседает без единой строки в логе.
_MAX_RUN_SECONDS = 100
_CAP_NS = "covers"


def _today() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


async def _used_today() -> int:
    used = await cache.get_counter(_CAP_NS, f"master_mirror:{_today()}")
    return used or 0


async def mirror_master_covers_batch() -> dict:
    """Один прогон. Возвращает счётчики — их же пишет в лог."""
    settings = get_settings()
    if not settings.master_mirror_enabled:
        return {"skipped": "disabled"}

    cap = settings.master_mirror_daily_cap
    used = await _used_today()
    if used >= cap:
        return {"skipped": "daily_cap", "used": used, "cap": cap}

    budget = min(settings.master_mirror_batch, cap - used)
    pace = settings.master_mirror_pace_sec

    from app.services.cover_storage import CoverStorageService
    from app.services.cover_demand import TRIGGER_BACKFILL

    service = CoverStorageService()
    started = time.monotonic()
    done = failed = already = 0

    async with async_session_maker() as db:
        rows = (await db.execute(
            text(
                "SELECT master_id, cover_image_url FROM discogs_master_covers "
                "WHERE cover_image_url IS NOT NULL "
                "  AND mirrored_at IS NULL "
                "  AND mirror_attempts < :max_att "
                # Платный канал отсекаем по ХОСТУ, а не по колонке source.
                # Колонка врёт: 9 215 строк с картинкой на i.discogs.com
                # помечены как caa/deezer/store или вовсе NULL (источник
                # проставлялся тем, кто нашёл СТРОКУ, а не тем, чья картинка).
                # Через фильтр по source они проходили и упирались в дневной
                # бюджет Discogs-картинок: прогон 15.09 в 17:00 дал 25 успехов
                # и 15 отказов — все 15 были именно такими строками. Отказ
                # стоит попытки, три попытки — и строка выпадает из очереди
                # навсегда, хотя мы её даже не пробовали качать по-настоящему.
                "  AND cover_image_url NOT LIKE '%i.discogs.com%' "
                # Свежий каталог вперёд: совпадает с витриной новинок и живым
                # спросом, как и порядок кандидатов у дрипа.
                "ORDER BY master_id DESC "
                "LIMIT :n"
            ),
            {"max_att": _MAX_ATTEMPTS, "n": budget},
        )).all()

        if not rows:
            return {"done": 0, "queue_empty": True}

        for i, row in enumerate(rows):
            if time.monotonic() - started > _MAX_RUN_SECONDS:
                break
            if i:
                await asyncio.sleep(pace)

            mid, url = row[0], row[1]

            # Уже в вечном слое — качать нечего. На старте очереди таких ~29
            # тысяч (их намирроривали попутно раньше), и без этой проверки
            # первые прогоны выкачивали бы их с чужих CDN заново, попутно
            # сжигая дневной потолок впустую.
            from app.services.s3_covers import cover_exists
            if await cover_exists(f"m{mid}"):
                await db.execute(
                    text(
                        "UPDATE discogs_master_covers SET mirrored_at = :now "
                        "WHERE master_id = :mid"
                    ),
                    {"now": datetime.utcnow(), "mid": mid},
                )
                await db.commit()
                already += 1
                continue

            try:
                stored = await service.download_and_store(
                    f"m{mid}", url, db, trigger=TRIGGER_BACKFILL,
                )
            except Exception:
                logger.warning("master mirror: %s упал", mid, exc_info=True)
                stored = None

            if stored:
                await db.execute(
                    text(
                        "UPDATE discogs_master_covers SET mirrored_at = :now "
                        "WHERE master_id = :mid"
                    ),
                    {"now": datetime.utcnow(), "mid": mid},
                )
                done += 1
                await cache.incr(_CAP_NS, f"master_mirror:{_today()}", ttl=172800)
            else:
                # Не вышло — считаем попытку. Исчерпав лимит, строка сама
                # выпадет из выборки: predicate смотрит на mirror_attempts.
                await db.execute(
                    text(
                        "UPDATE discogs_master_covers "
                        "SET mirror_attempts = mirror_attempts + 1 "
                        "WHERE master_id = :mid"
                    ),
                    {"mid": mid},
                )
                failed += 1
            # Commit на строку: прогон длится до 100с, копившаяся транзакция
            # держала бы row-locks против соседних бэкфиллов.
            await db.commit()

    if done or failed or already:
        logger.info(
            "master mirror: %d зеркалировано, %d уже в бакете, %d не вышло "
            "(за сутки %d из %d)",
            done, already, failed, used + done, cap,
        )
    return {
        "done": done, "already": already, "failed": failed,
        "used_today": used + done, "cap": cap,
    }
