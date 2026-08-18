"""Сторож свободного места на диске.

Зачем отдельная задача. Алертов у нас хватало — покрытие обложек, доля ошибок,
квоты, штормы rate-limit, — но за диском не следил никто. А кончившийся диск
ломает не картинки: Postgres перестаёт писать, и это полноценная авария, а не
деградация. Узнать о ней по упавшему приложению — худший из возможных способов.

Замер 18.08.2026: свободно 8.8 ГБ из 38, обложки прибавляют ~280 МБ в сутки
(4 320 файлов по 65 КБ) на одних фоновых джобах, без пользователей. То есть
запас примерно месяц, и он сокращается по мере роста каталога.

Два порога вместо одного. Предупреждение даёт время спокойно разобраться
(почистить docker, перенести обложки в объектное хранилище), критический — это
уже «бросай всё». Разные ключи троттлинга, чтобы предупреждение не глушило
критический алерт.

Заодно считаем, сколько занимают обложки: если основной едок — они, лечится
переездом в бакет; если Postgres или docker — лечится иначе, и сообщение это
подсказывает.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import get_settings
from app.services import alerts

logger = logging.getLogger(__name__)

# Порог предупреждения — с запасом на неделю при текущем темпе роста.
_WARN_FREE_GB = 6.0
# Критический: суток на реакцию при любом мыслимом темпе.
_CRIT_FREE_GB = 2.5



def _dir_size_gb(path: Path) -> float:
    """Размер каталога в ГБ. Недоступен — 0.0, метрика не должна ронять джобу."""
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(total / 1024 ** 3, 2)
    except OSError:
        return 0.0


async def check_disk_space() -> dict:
    """Проверить свободное место, при нехватке — алерт. Возвращает срез."""
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        logger.warning("disk guard: не удалось прочитать статистику диска", exc_info=True)
        return {}

    free_gb = round(usage.free / 1024 ** 3, 2)
    total_gb = round(usage.total / 1024 ** 3, 2)
    used_pct = round(100 * usage.used / usage.total, 1)

    covers_gb = _dir_size_gb(Path(get_settings().covers_dir))

    snapshot = {
        "free_gb": free_gb,
        "total_gb": total_gb,
        "used_pct": used_pct,
        "covers_gb": covers_gb,
    }
    logger.info("disk: свободно %.1f ГБ из %.1f (занято %.1f%%), обложки %.1f ГБ",
                free_gb, total_gb, used_pct, covers_gb)

    if free_gb <= _CRIT_FREE_GB:
        alerts.fire_and_forget(
            key="disk_space_critical",
            title=f"Диск: осталось {free_gb} ГБ",
            body=_body(snapshot, critical=True),
        )
    elif free_gb <= _WARN_FREE_GB:
        alerts.fire_and_forget(
            key="disk_space_low",
            title=f"Диск: осталось {free_gb} ГБ из {total_gb}",
            body=_body(snapshot, critical=False),
        )
    return snapshot


def _body(s: dict, *, critical: bool) -> str:
    """Текст алерта с подсказкой, куда смотреть, — иначе он бесполезен в 3 ночи."""
    head = (
        "Postgres скоро перестанет писать — это авария, а не деградация.\n"
        if critical else
        "Время разобраться спокойно, пока не горит.\n"
    )
    return (
        f"{head}"
        f"Занято {s['used_pct']}%, обложки — {s['covers_gb']} ГБ.\n\n"
        "Что обычно съедает место, по убыванию отдачи:\n"
        "1. docker builder prune -f — build cache, освобождает гигабайты и безопасен;\n"
        "2. неиспользуемые образы (осторожно: предыдущий образ нужен для отката blue-green);\n"
        "3. обложки — растут ~280 МБ/сутки, лечится переездом в объектное хранилище;\n"
        "4. дампы Discogs в Postgres — самая крупная, но статичная часть."
    )
