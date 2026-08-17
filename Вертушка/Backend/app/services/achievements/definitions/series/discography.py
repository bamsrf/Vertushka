"""Серия «Полная дискография» (H* + META_depth).

Считает по ЛОКАЛЬНОМУ дамп-индексу, без единого вызова Discogs. Дискография
артиста берётся из `discogs_releases_index` (artist_ids + master_id), тип
релиза — через `services/release_type.py`, единственный источник правды по
классификации. Своих регексов здесь нет намеренно: в проекте это уже приводило
к расхождению правил между SQL и питоном.

«Студийный альбом» = мастер-группа, которую classify_group признал `album`.
Отсекаются compilation, live/промо (они уходят в `other` через служебные
маркеры), EP и синглы. Данные дампа по формату неполны, поэтому H2 подстрахован
двумя порогами: артист учитывается только если у него ≥3 студийных альбомов
(иначе «полная дискография» выдавалась бы за одну пластинку) и если юзер владеет
хотя бы 3 его записями.

H2 — тяжёлая проверка (группировка по всем релизам артиста), поэтому висит
ТОЛЬКО на daily_tick. Остальные считаются на добавление.

ОТЛИЧИЕ ОТ ИСХОДНОГО ПЛАНА: динамические коды `H2:<artist-slug>` /
`H4:<master-slug>` / `H5:<label-slug>` не реализованы — ачивка открывается один
раз за любого артиста/мастера/лейбл, а имя кладётся в `ach_metadata` для UI.
Составные коды требуют изменений в registry и в экране ачивок; см.
PLAN_ACHIEVEMENTS_V2.md §4.10.

Состав:
- H1 «Поклонник»       — 5 пластинок одного артиста
- H2 «Полная»          — все студийные альбомы артиста
- H3 «Сравнил»         — 3+ разных пресса одного мастера
- H4 «Археолог»        — 5+ разных прессов одного мастера
- H5 «Лейбл-фанат»     — 20 пластинок одного лейбла
- META_depth «Учёный»  — H2 + H4 + H5 (любые). Награда: title с именем артиста.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record
from app.models.user_achievement import UserAchievement
from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK
from app.services.achievements.registry import (
    AchievementDefinition,
    AchievementTier,
    EvalResult,
)
from app.services.release_type import ALBUM, classify_group

logger = logging.getLogger(__name__)


H1_CODE = "H1_artist_x5"
H2_CODE = "H2_artist_studio_full"
H3_CODE = "H3_master_pressings_3"
H4_CODE = "H4_master_pressings_5"
H5_CODE = "H5_label_x20"
META_CODE = "META_depth"
DISCOGRAPHY_CODES = {H1_CODE, H2_CODE, H3_CODE, H4_CODE, H5_CODE}


H1_TARGET = 5      # пластинок одного артиста
H3_TARGET = 3      # прессов одного мастера
H4_TARGET = 5      # прессов одного мастера (эпик)
H5_TARGET = 20     # пластинок одного лейбла

#: Порог «дискография вообще заслуживает называться полной». Артист с одним
#: студийником иначе отдавал бы эпическую ачивку за одну покупку.
H2_MIN_ALBUMS = 3
#: Сколько записей артиста должно быть у юзера, чтобы вообще проверять H2.
#: Прежде всего это ограничитель стоимости: без него daily_tick перебирал бы
#: каждого артиста коллекции, включая тех, у кого куплен один сингл.
H2_MIN_OWNED = 3
#: Потолок артистов на один прогон. Коллекция в тысячу пластинок — это сотни
#: артистов, и полный перебор растянул бы daily_tick на всех пользователей.
H2_MAX_CANDIDATES = 25


def _default_collection_id(user_id: UUID):
    """Основная коллекция (минимальный sort_order) — папки не накручивают."""
    return (
        select(Collection.id)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order, Collection.created_at)
        .limit(1)
        .scalar_subquery()
    )


async def _max_count_by(db: AsyncSession, user_id: UUID, column) -> tuple[int, str | None]:
    """Максимум COUNT(DISTINCT record_id) по группам column + само значение.

    Возвращает (сколько, что именно) — второе идёт в ach_metadata, чтобы экран
    ачивок мог показать «5 пластинок Radiohead», а не безымянное число.
    """
    rows = await db.execute(
        select(column, func.count(func.distinct(CollectionItem.record_id)).label("n"))
        .join(Record, Record.id == CollectionItem.record_id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            column.is_not(None),
            column != "",
        )
        .group_by(column)
        .order_by(text("n DESC"))
        .limit(1)
    )
    row = rows.first()
    if row is None:
        return 0, None
    value, count = row
    return int(count or 0), value


async def _evaluate_h1(db, user_id, payload, unlocked_now) -> EvalResult:
    """5 пластинок одного артиста."""
    count, artist = await _max_count_by(db, user_id, func.lower(Record.artist))
    return EvalResult(
        unlocked=count >= H1_TARGET,
        progress=min(count, H1_TARGET),
        progress_target=H1_TARGET,
        metadata={"artist_name": artist} if artist else None,
    )


async def _max_pressings_per_master(
    db: AsyncSession, user_id: UUID
) -> tuple[int, str | None]:
    """Больше всего разных прессов одного мастера + название мастера.

    Пресс = отдельный Record с тем же discogs_master_id. Именно поэтому
    обогащение импорта из дампа важно для этой пары ачивок: у «тонкой»
    импортированной записи master_id пустой, и все прессы выглядят
    несвязанными.
    """
    rows = await db.execute(
        select(
            Record.discogs_master_id,
            func.count(func.distinct(CollectionItem.record_id)).label("n"),
            func.min(Record.title).label("title"),
        )
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.discogs_master_id.is_not(None),
            Record.discogs_master_id != "",
        )
        .group_by(Record.discogs_master_id)
        .order_by(text("n DESC"))
        .limit(1)
    )
    row = rows.first()
    if row is None:
        return 0, None
    _master_id, count, title = row
    return int(count or 0), title


def _make_pressings_evaluator(target: int):
    async def evaluator(db, user_id, payload, unlocked_now) -> EvalResult:
        count, title = await _max_pressings_per_master(db, user_id)
        return EvalResult(
            unlocked=count >= target,
            progress=min(count, target),
            progress_target=target,
            metadata={"master_name": title} if title else None,
        )
    return evaluator


async def _evaluate_h5(db, user_id, payload, unlocked_now) -> EvalResult:
    """20 пластинок одного лейбла."""
    count, label = await _max_count_by(db, user_id, func.lower(Record.label))
    return EvalResult(
        unlocked=count >= H5_TARGET,
        progress=min(count, H5_TARGET),
        progress_target=H5_TARGET,
        metadata={"label_name": label} if label else None,
    )


# --- H2: полная студийная дискография ---------------------------------------

#: Кандидаты в H2: артисты дампа, чьих релизов у юзера больше всего.
#: `artist_ids @> ARRAY[...]` не годится для обратной задачи, поэтому идём от
#: принадлежащих юзеру discogs_id и разворачиваем их artist_ids.
_H2_CANDIDATES_SQL = text(
    """
    SELECT aid, COUNT(*) AS owned
    FROM (
        SELECT unnest(i.artist_ids) AS aid
        FROM discogs_releases_index i
        WHERE i.discogs_id = ANY(:ids)
          AND i.artist_ids IS NOT NULL
    ) src
    GROUP BY aid
    HAVING COUNT(*) >= :min_owned
    ORDER BY owned DESC
    LIMIT :max_candidates
    """
)

#: Все мастер-группы артиста с форматами всех версий — та же форма, что в
#: discogs_index.get_artist_masters_local: format_full несёт полный список
#: описаний, format_type только первое (усечение при ингесте).
_H2_ARTIST_MASTERS_SQL = text(
    """
    SELECT
        COALESCE(i.master_id, i.discogs_id) AS gid,
        array_agg(DISTINCT COALESCE(f.format_full, i.format_type)) AS fmts,
        array_agg(DISTINCT i.discogs_id) AS release_ids
    FROM discogs_releases_index i
    LEFT JOIN discogs_release_formats f ON f.discogs_id = i.discogs_id
    WHERE i.artist_ids @> ARRAY[CAST(:aid AS bigint)]
      AND NOT i.is_unofficial
    GROUP BY COALESCE(i.master_id, i.discogs_id)
    """
)


async def _owned_discogs_ids(db: AsyncSession, user_id: UUID) -> list[int]:
    """Числовые discogs_id из основной коллекции. Ручные релизы отсеиваются."""
    rows = await db.execute(
        select(func.distinct(Record.discogs_id))
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .where(
            CollectionItem.collection_id == _default_collection_id(user_id),
            Record.discogs_id.is_not(None),
        )
    )
    return [int(d) for (d,) in rows.all() if d and str(d).isdigit()]


async def _evaluate_h2(db, user_id, payload, unlocked_now) -> EvalResult:
    """Собрана ли ПОЛНАЯ студийная дискография хоть одного артиста.

    Fail-soft: если дамп-индекс недоступен или у артиста нет строк, ачивка
    просто не открывается — падать система ачивок не должна (её ошибки и так
    глушит evaluator, но тихий None лучше исключения в логе на каждый тик).
    """
    owned_ids = await _owned_discogs_ids(db, user_id)
    if not owned_ids:
        return EvalResult(unlocked=False, progress=0, progress_target=H2_MIN_ALBUMS)

    try:
        candidates = (await db.execute(
            _H2_CANDIDATES_SQL,
            {
                "ids": owned_ids,
                "min_owned": H2_MIN_OWNED,
                "max_candidates": H2_MAX_CANDIDATES,
            },
        )).all()
    except Exception as e:  # noqa: BLE001 — нет дампа → нет ачивки, не падаем
        logger.warning("H2: candidate lookup failed: %s", e)
        return EvalResult(unlocked=False)

    owned_set = set(owned_ids)
    best_ratio: tuple[int, int] = (0, H2_MIN_ALBUMS)  # (собрано, всего)
    best_artist: str | None = None

    for artist_id, _owned in candidates:
        try:
            masters = (await db.execute(
                _H2_ARTIST_MASTERS_SQL, {"aid": int(artist_id)}
            )).all()
        except Exception as e:  # noqa: BLE001
            logger.warning("H2: masters lookup failed for %s: %s", artist_id, e)
            continue

        studio_total = 0
        studio_owned = 0
        for _gid, fmts, release_ids in masters:
            if classify_group(list(fmts or [])) != ALBUM:
                continue
            studio_total += 1
            # Мастер засчитан, если у юзера есть ЛЮБОЙ его пресс: «собрал
            # альбом» — про альбом, а не про конкретное издание.
            if owned_set.intersection(release_ids or []):
                studio_owned += 1

        if studio_total < H2_MIN_ALBUMS:
            continue
        if studio_owned > best_ratio[0] or (
            studio_owned == best_ratio[0] and studio_total < best_ratio[1]
        ):
            best_ratio = (studio_owned, studio_total)
            best_artist = str(artist_id)

        if studio_owned >= studio_total:
            return EvalResult(
                unlocked=True,
                progress=studio_owned,
                progress_target=studio_total,
                metadata={"artist_id": str(artist_id), "albums": studio_total},
            )

    return EvalResult(
        progress=best_ratio[0],
        progress_target=best_ratio[1],
        metadata={"artist_id": best_artist} if best_artist else None,
    )


async def _evaluate_meta_depth(db, user_id, payload, unlocked_now) -> EvalResult:
    """META закрывается, когда открыты H2, H4 и H5."""
    required = {H2_CODE, H4_CODE, H5_CODE}
    persisted = await db.execute(
        select(UserAchievement.code).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code.in_(required),
            UserAchievement.is_unlocked.is_(True),
        )
    )
    unlocked = set(persisted.scalars().all()) | (unlocked_now & required)
    progress = len(unlocked)
    target = len(required)
    return EvalResult(
        unlocked=progress >= target, progress=progress, progress_target=target
    )


DEFINITIONS: list[AchievementDefinition] = [
    AchievementDefinition(
        code=H1_CODE,
        title_ru="Поклонник",
        description_ru="5 пластинок одного артиста.",
        description_done_ru="5 пластинок одного артиста собрано.",
        series="discography",
        tier=AchievementTier.SIMPLE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_h1,
        icon_slug="h1_artist_x5",
    ),
    AchievementDefinition(
        code=H2_CODE,
        title_ru="Полная",
        description_ru="Собрал все студийные альбомы артиста.",
        description_done_ru="Полная студийная дискография собрана.",
        series="discography",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        # Только daily_tick: перебор дискографий до 25 артистов
        # непозволительно дорог на каждое добавление пластинки.
        triggers=(DAILY_TICK,),
        evaluator=_evaluate_h2,
        flavor_ru="Discogs больше нечего показать.",
        icon_slug="h2_artist_studio_full",
    ),
    AchievementDefinition(
        code=H3_CODE,
        title_ru="Сравнил",
        description_ru="3+ разных пресса одного мастера.",
        description_done_ru="3 пресса одного мастера собрано.",
        series="discography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_pressings_evaluator(H3_TARGET),
        icon_slug="h3_master_pressings_3",
    ),
    AchievementDefinition(
        code=H4_CODE,
        title_ru="Археолог",
        description_ru="5+ разных прессов одного мастера.",
        description_done_ru="5 прессов одного мастера собрано.",
        series="discography",
        tier=AchievementTier.EPIC,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_make_pressings_evaluator(H4_TARGET),
        icon_slug="h4_master_pressings_5",
    ),
    AchievementDefinition(
        code=H5_CODE,
        title_ru="Лейбл-фанат",
        description_ru="20 пластинок одного лейбла.",
        description_done_ru="20 пластинок одного лейбла собрано.",
        series="discography",
        tier=AchievementTier.RARE,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_h5,
        icon_slug="h5_label_x20",
    ),
    AchievementDefinition(
        code=META_CODE,
        title_ru="Учёный",
        description_ru="Открой «Полную», «Археолога» и «Лейбл-фаната».",
        description_done_ru="«Полная», «Археолог» и «Лейбл-фанат» закрыты.",
        series="discography",
        tier=AchievementTier.LEGEND,
        is_hidden=False,
        triggers=(COLLECTION_ITEM_ADDED, DAILY_TICK),
        evaluator=_evaluate_meta_depth,
        is_meta=True,
        flavor_ru="Тиражи признали тебя.",
        icon_slug="meta_depth",
    ),
]
