"""Форматные серии: FMT (кросс-формат), T (кассеты), CD, BX (бокс-сеты).

Каталог исторически крутился вокруг винила — эти серии закрывают пробел.

Как считаем. Носитель определяется по `Record.format_type` +
`Record.format_description` через `media_format.parse_media()` (там же разобраны
грабли с бокс-сетами и семьёй CD). Запись может попасть сразу в два семейства:
бокс из четырёх винилов — и винил, и бокс.

Анти-фарм — как в scale.py: только ОСНОВНАЯ коллекция и только записи старше
24 часов. Иначе «добавил 25 кассет, забрал ачивку, удалил» проходит на ура.

Серии T / CD / BX показываются в приложении не сразу: пока у юзера нет ни одной
единицы формата, серия не приходит в /achievements/me вообще (фильтр в
`_group_series`). Полка с кассетами появляется в тот момент, когда появляется
первая кассета.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.media_format import (
    BOX_SET,
    CASSETTE,
    CD,
    FAMILIES,
    VINYL,
    parse_media,
)
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)

ANTIFARM_COOLDOWN = timedelta(hours=24)

FMT1_CODE = "FMT1_beyond_vinyl"
FMT2_CODE = "FMT2_multiformat"
FMT3_CODE = "FMT3_all_formats"
META_FORMATS_CODE = "META_formats"

T1_CODE = "T1_first_tape"
T2_CODE = "T2_tapes_x10"
T3_CODE = "T3_tapes_x25"
T4_CODE = "T4_tapes_x50"

CD1_CODE = "CD1_first_cd"
CD2_CODE = "CD2_cds_x25"
CD3_CODE = "CD3_cds_x100"
CD4_CODE = "CD4_cds_x250"

BX1_CODE = "BX1_first_box"
BX2_CODE = "BX2_boxes_x5"
BX3_CODE = "BX3_boxes_x15"

#: Серии, у которых первая ачивка открывает саму полку в UI.
GATE_CODE_BY_SERIES = {
    "cassettes": T1_CODE,
    "cds": CD1_CODE,
    "boxsets": BX1_CODE,
}

_FMT_CODES = {FMT1_CODE, FMT2_CODE, FMT3_CODE}
_META_MIN_PER_FAMILY = 10


async def _load_media(db: AsyncSession, user_id: UUID) -> list:
    """Носители всех «отлежавшихся» записей основной коллекции юзера.

    Тянем два текстовых поля на запись: разбирать описания приходится в Python
    (бокс-сет опознаётся по подстроке в описании, в SQL это нечитаемо).
    """
    cutoff = datetime.utcnow() - ANTIFARM_COOLDOWN
    default_collection_id = (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(Record.format_type, Record.format_description)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(
            CollectionItem.collection_id == default_collection_id,
            CollectionItem.added_at <= cutoff,
        )
        .distinct(Record.id)
    )
    return [parse_media(ft, fd) for ft, fd in rows.all()]


def _counts(media: list) -> dict[str, int]:
    counts = {family: 0 for family in FAMILIES}
    for info in media:
        for family in info.families:
            counts[family] += 1
    return counts


def _make_family_threshold(family: str, threshold: int):
    """N единиц конкретного носителя в коллекции."""

    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        count = _counts(await _load_media(db, user_id))[family]
        return EvalResult(
            unlocked=count >= threshold,
            progress=min(count, threshold),
            progress_target=threshold,
        )

    return evaluator


def _make_distinct_families(target: int):
    """N разных типов носителя в коллекции."""

    async def evaluator(
        db: AsyncSession,
        user_id: UUID,
        payload: dict[str, Any],
        unlocked_now: set[str],
    ) -> EvalResult:
        counts = _counts(await _load_media(db, user_id))
        distinct = sum(1 for family in FAMILIES if counts[family] > 0)
        return EvalResult(
            unlocked=distinct >= target,
            progress=min(distinct, target),
            progress_target=target,
        )

    return evaluator


async def _evaluate_beyond_vinyl(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """Первый не-винил: кассета, CD или бокс."""
    counts = _counts(await _load_media(db, user_id))
    non_vinyl = sum(counts[f] for f in FAMILIES if f != VINYL)
    return EvalResult(unlocked=non_vinyl > 0, progress=min(non_vinyl, 1), progress_target=1)


async def _evaluate_meta_formats(
    db: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    unlocked_now: set[str],
) -> EvalResult:
    """FMT1–FMT3 открыты И минимум по 10 единиц каждого формата."""
    rows = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_unlocked.is_(True),
            UserAchievement.code.in_(list(_FMT_CODES)),
        )
    )
    unlocked = set(rows.scalars().all()) | (unlocked_now & _FMT_CODES)
    if unlocked != _FMT_CODES:
        return EvalResult(progress=len(unlocked), progress_target=len(_FMT_CODES))

    counts = _counts(await _load_media(db, user_id))
    deep = sum(1 for family in FAMILIES if counts[family] >= _META_MIN_PER_FAMILY)
    return EvalResult(
        unlocked=deep == len(FAMILIES),
        progress=deep,
        progress_target=len(FAMILIES),
    )


_TRIGGERS = (COLLECTION_ITEM_ADDED, DAILY_TICK)


def _fmt(code, title, desc, tier, evaluator, flavor, slug, series, done=None):
    return AchievementDefinition(
        code=code,
        title_ru=title,
        description_ru=desc,
        description_done_ru=done or "",
        series=series,
        tier=tier,
        is_hidden=False,
        triggers=_TRIGGERS,
        evaluator=evaluator,
        flavor_ru=flavor,
        icon_slug=slug,
    )


DEFINITIONS: list[AchievementDefinition] = [
    # --- Кросс-формат -------------------------------------------------------
    _fmt(
        FMT1_CODE, "За пределами винила",
        "Добавь в коллекцию первый не-винил: кассету, CD или бокс-сет.",
        AchievementTier.SIMPLE, _evaluate_beyond_vinyl,
        "Музыка жила не только в бороздке.", "fmt1_beyond_vinyl", "formats",
        done="Первый не-винил в коллекции: кассета, CD или бокс-сет.",
    ),
    _fmt(
        FMT2_CODE, "Мультиформат",
        "Собери три разных типа носителя.",
        AchievementTier.NOTABLE, _make_distinct_families(3),
        "Носитель — дело вкуса, а не веры.", "fmt2_multiformat", "formats",
        done="Три разных типа носителя на одной полке.",
    ),
    _fmt(
        FMT3_CODE, "Всеформатный",
        "Собери все четыре типа: винил, кассету, CD и бокс-сет.",
        AchievementTier.RARE, _make_distinct_families(4),
        "Полный комплект носителей эпохи.", "fmt3_all_formats", "formats",
        done="Собраны все четыре носителя: винил, кассета, CD и бокс-сет.",
    ),
    _fmt(
        META_FORMATS_CODE, "Без предрассудков",
        "Открой FMT1–FMT3 и собери по 10 единиц каждого формата.",
        AchievementTier.EPIC, _evaluate_meta_formats,
        "Ты не споришь о носителях. Ты их собираешь.", "meta_formats", "formats",
        done="Все кросс-форматные ачивки открыты, и каждого формата — не меньше 10 штук.",
    ),
    # --- Кассеты ------------------------------------------------------------
    _fmt(
        T1_CODE, "Перемотка", "Добавь первую кассету.",
        AchievementTier.SIMPLE, _make_family_threshold(CASSETTE, 1),
        "Карандаш в бобину — и поехали.", "t1_first_tape", "cassettes",
        done="Первая кассета в коллекции.",
    ),
    _fmt(
        T2_CODE, "Микстейп", "Собери 10 кассет.",
        AchievementTier.SIMPLE, _make_family_threshold(CASSETTE, 10),
        "Сторона А кончается на самом интересном.", "t2_tapes_x10", "cassettes",
        done="10 кассет в коллекции.",
    ),
    _fmt(
        T3_CODE, "Хром и металл", "Собери 25 кассет.",
        AchievementTier.NOTABLE, _make_family_threshold(CASSETTE, 25),
        "Плёнка бывает разной. Ты уже слышишь разницу.", "t3_tapes_x25", "cassettes",
        done="25 кассет в коллекции.",
    ),
    _fmt(
        T4_CODE, "Эпоха Walkman", "Собери 50 кассет.",
        AchievementTier.RARE, _make_family_threshold(CASSETTE, 50),
        "Целая эпоха помещалась в карман.", "t4_tapes_x50", "cassettes",
        done="50 кассет в коллекции.",
    ),
    # --- CD -----------------------------------------------------------------
    _fmt(
        CD1_CODE, "Лазер включён", "Добавь первый CD.",
        AchievementTier.SIMPLE, _make_family_threshold(CD, 1),
        "Никаких щелчков. Пока непривычно.", "cd1_first_cd", "cds",
        done="Первый CD в коллекции.",
    ),
    _fmt(
        CD2_CODE, "Jewel Case", "Собери 25 компактов.",
        AchievementTier.SIMPLE, _make_family_threshold(CD, 25),
        "Трещина на боксе — обязательная часть комплекта.", "cd2_cds_x25", "cds",
        done="25 компактов в коллекции.",
    ),
    _fmt(
        CD3_CODE, "Серебряная полка", "Собери 100 компактов.",
        AchievementTier.NOTABLE, _make_family_threshold(CD, 100),
        "Сотня зеркал в ряд.", "cd3_cds_x100", "cds",
        done="100 компактов в коллекции.",
    ),
    _fmt(
        CD4_CODE, "Ярче павлина", "Собери 250 компактов.",
        AchievementTier.RARE, _make_family_threshold(CD, 250),
        "Формат, который хоронили тридцать лет подряд.", "cd4_cds_x250", "cds",
        done="250 компактов в коллекции.",
    ),
    # --- Бокс-сеты ----------------------------------------------------------
    _fmt(
        BX1_CODE, "Распаковка", "Добавь первый бокс-сет.",
        AchievementTier.NOTABLE, _make_family_threshold(BOX_SET, 1),
        "Коробка тяжелее, чем кажется.", "bx1_first_box", "boxsets",
        done="Первый бокс-сет в коллекции.",
    ),
    _fmt(
        BX2_CODE, "Полка ломится", "Собери 5 бокс-сетов.",
        AchievementTier.RARE, _make_family_threshold(BOX_SET, 5),
        "Полка начинает прогибаться.", "bx2_boxes_x5", "boxsets",
        done="5 бокс-сетов в коллекции.",
    ),
    _fmt(
        BX3_CODE, "Хранилище делюксов", "Собери 15 бокс-сетов.",
        AchievementTier.EPIC, _make_family_threshold(BOX_SET, 15),
        "Это уже не полка. Это архив.", "bx3_boxes_x15", "boxsets",
        done="15 бокс-сетов в коллекции.",
    ),
]
