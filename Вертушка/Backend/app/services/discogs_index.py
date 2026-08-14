"""Дозапись одиночных Discogs-релизов в discogs_releases_index (search-индекс).

Обычно индекс наполняется батч-ингестом дампа (scripts/ingest_discogs_dump.py).
Но дамп устаревает — свежие релизы, добытые из live Discogs API, в нём
отсутствуют. Этот helper кладёт такой релиз в индекс «на лету», чтобы
`/records/search` нашёл его в следующий раз. См. docs/plans/USER_SUBMITTED_RECORDS
и план Discogs-first.

Единая точка вызова — api/records.py::get_or_create_record_by_discogs_id: любой
впервые открытый/добавленный Discogs-релиз обогащает индекс.
"""
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scrapers.extractors import normalize_barcode, normalize_catalog

logger = logging.getLogger(__name__)


async def filter_artist_names_with_releases(
    db: AsyncSession, names: list[str]
) -> set[str]:
    """Из списка имён артистов вернуть множество (lower-cased) тех, у кого в
    локальном дамп-индексе есть хоть один релиз — по производной таблице
    discogs_artist_names (btree PK, index-scan, без вызовов Discogs).

    Жёсткий фильтр выдачи поиска: имя не вернулось → у артиста нет релизов в
    дампе → дроп. Fail-open: при ошибке БД возвращаем все имена (поиск не
    деградирует), вызывающий тогда никого не дропает.
    """
    norm = {n.strip().lower() for n in names if n and n.strip()}
    if not norm:
        return set()
    try:
        rows = await db.execute(
            text(
                "SELECT name_norm FROM discogs_artist_names "
                "WHERE name_norm = ANY(:names)"
            ),
            {"names": list(norm)},
        )
        return {r[0] for r in rows}
    except Exception as e:  # noqa: BLE001 — fail-open, не роняем поиск
        logger.warning("filter_artist_names_with_releases failed: %s", e)
        return norm  # все «прошли» → дропа не будет


async def get_artist_masters_local(
    db: AsyncSession,
    artist_id: str,
    page: int = 1,
    per_page: int = 100,
    sort_order: str = "desc",
):
    """Дискография артиста из ЛОКАЛЬНОГО дамп-индекса — ноль вызовов Discogs.

    Требует backfill artist_ids (scripts/load_artist_map.py). Группирует
    релизы по master_id (release-only без мастера — отдельные карточки с
    master_id="r{release_id}", как в live-пути). Возвращает None, когда у
    артиста нет строк в индексе (новый/не залитый артист) — caller падает
    обратно на live Discogs.

    Обложки — cover_image_url индекса (CAA-маппинг + drip); отсутствующие
    дойдут фоном, клиент терпит null.
    """
    from app.schemas.record import MasterSearchResponse, MasterSearchResult
    from app.services.release_type import classify_group

    if not str(artist_id).isdigit():
        return None

    name_row = (await db.execute(
        text("SELECT name FROM discogs_artists WHERE artist_id = :aid"),
        {"aid": int(artist_id)},
    )).scalar()
    if not name_row:
        return None

    order = "DESC" if sort_order != "asc" else "ASC"
    rows = (await db.execute(
        text(f"""
            WITH grp AS (
                SELECT
                    COALESCE(master_id, discogs_id) AS gid,
                    (master_id IS NULL) AS release_only,
                    MIN(year) AS year,
                    (array_agg(title ORDER BY year ASC NULLS LAST, discogs_id))[1] AS title,
                    (array_agg(cover_image_url ORDER BY (cover_image_url IS NULL), year ASC NULLS LAST))[1] AS cover,
                    (array_agg(fmt ORDER BY year ASC NULLS LAST, discogs_id))[1] AS format_type,
                    -- Форматы ВСЕХ версий группы: тип считает release_type.py,
                    -- а не SQL-регексы. Дублирующие правила здесь и в питоне
                    -- расходились (umd был в _is_video, но не в регексе) и
                    -- чинились точечно. DISTINCT ограничивает размер массива у
                    -- мастеров с сотнями изданий, голосованию хватает.
                    array_agg(DISTINCT fmt) AS fmts,
                    MIN(discogs_id) AS main_release_id
                FROM (
                    -- format_full несёт ВСЕ описания Discogs, format_type —
                    -- только первое (усечение в ingest). Без полного списка
                    -- 'Vinyl, 12", 33 ⅓ RPM, EP' лежит как 'Vinyl, 12"' и EP
                    -- уходит в синглы, а 'Vinyl, LP, Transcription' (radio-show)
                    -- выглядит альбомом. Строки с 0-1 описанием в side-таблицу
                    -- не пишутся — там COALESCE и так берёт format_type.
                    SELECT i.discogs_id, i.master_id, i.year, i.title,
                           i.cover_image_url,
                           COALESCE(f.format_full, i.format_type) AS fmt
                    FROM discogs_releases_index i
                    LEFT JOIN discogs_release_formats f
                        ON f.discogs_id = i.discogs_id
                    WHERE i.artist_ids @> ARRAY[CAST(:aid AS bigint)]
                    AND NOT i.is_unofficial
                ) src
                GROUP BY COALESCE(master_id, discogs_id), (master_id IS NULL)
            ),
            dedup AS (
                SELECT * FROM grp WHERE NOT release_only
                UNION ALL
                SELECT * FROM grp g
                WHERE g.release_only AND NOT EXISTS (
                    SELECT 1 FROM grp m
                    WHERE NOT m.release_only AND lower(m.title) = lower(g.title)
                )
            )
            SELECT d.gid, d.release_only, d.year, d.title, d.format_type,
                   d.fmts,
                   d.main_release_id,
                   COALESCE(d.cover, mc.cover_image_url) AS cover,
                   COUNT(*) OVER () AS total
            FROM dedup d
            LEFT JOIN discogs_master_covers mc
                ON NOT d.release_only AND mc.master_id = d.gid
            ORDER BY d.year {order} NULLS LAST, d.gid
            LIMIT :lim OFFSET :off
        """),
        {"aid": int(artist_id), "lim": per_page, "off": (page - 1) * per_page},
    )).mappings().all()

    if not rows and page == 1:
        return None  # артиста нет в индексе → live fallback

    # Обложки — через собственное зеркало /covers/: nginx-статика после
    # первого обращения (archive.org из РФ — секунды, наш сервер — мс).
    # Стабильный имён-неймспейс: мастер → m{gid}.jpg, release-only → {id}.jpg;
    # fallback в covers.py резолвит источник по этим же таблицам.
    from app.config import get_settings
    covers_base = get_settings().public_covers_base

    total = rows[0]["total"] if rows else 0
    results = []
    for r in rows:
        release_only = r["release_only"]
        # У release-only группа = один релиз, его формат достоверен. У мастера
        # голосуем по всем изданиям: одиночный representative — случайный
        # (DVD-A издание альбома ложно уводило бы флагман в "other").
        release_type = classify_group(
            [r["format_type"]] if release_only else (r["fmts"] or [])
        )
        if r["cover"]:
            mirror_name = f"{r['main_release_id']}" if release_only else f"m{r['gid']}"
            cover_url = f"{covers_base}/{mirror_name}.jpg"
        else:
            cover_url = None
        results.append(MasterSearchResult(
            master_id=f"r{r['gid']}" if release_only else str(r["gid"]),
            title=r["title"] or "",
            artist=name_row,
            year=r["year"],
            main_release_id=str(r["main_release_id"]),
            cover_image_url=cover_url,
            thumb_image_url=None,
            release_type=release_type,
        ))

    # Самолечение обложек, два уровня:
    # 1) Batch-прогрев мастеров артиста: 1-3 Search-вызова закрывают до 300
    #    обложек разом → discogs_master_covers (NX-лок 6ч на артиста).
    # 2) Release-only карточки — через warm_dump_covers (CAA mb-map → barcode
    #    → Discogs budget → iTunes).
    # Клиент ретраит страницу через пару секунд и получает уже без заглушек.
    uncovered_masters = any(
        not r.cover_image_url and not r.master_id.startswith("r") for r in results
    )
    if uncovered_masters:
        from app.services.cover_warm import schedule_warm_artist_master_covers
        schedule_warm_artist_master_covers(str(artist_id), name_row)

    # Все непокрытые карточки (и мастера, и release-only) — через
    # warm_dump_covers по main_release_id: Search-батч выше покрывает только
    # топ-500 мастеров артиста, хвост синглов добирается поштучно
    # (CAA mb-map → barcode → Discogs budget → iTunes), найденное пишется в
    # строку индекса и сетка подхватит через array_agg.
    uncovered_releases = [
        r.main_release_id for r in results
        if not r.cover_image_url and r.main_release_id.isdigit()
    ]
    if uncovered_releases:
        from app.services.cover_warm import schedule_warm_dump_covers
        # Бюджет 10: release-only обскур добирается прямым get_release, но это
        # дорого против Discogs 60/мин. Массовое наполнение — bulk-backfill
        # (Deezer, бесплатно). 40/заход насыщал лимитер (429 + таймауты
        # version-detail) — при 1000 юзеров недопустимо. 10 трикл + NX-лок 6ч.
        schedule_warm_dump_covers(uncovered_releases, discogs_budget=10)

    # 3) Финальное звено — прямой get_master по непокрытым мастерам страницы.
    # Search (уровень 1) хоронит обскур (ремиксы/сплиты/компиляции), а прямой
    # /masters/{id} несёт обложку всегда (это же грузит тап). Bounded капом +
    # semaphore + NX-лок 6ч. Закрывает заглушки, что не нашёл никто.
    uncovered_master_ids = [
        r.master_id for r in results
        if not r.cover_image_url and r.master_id.isdigit() and r.master_id != "0"
    ]
    if uncovered_master_ids:
        from app.services.cover_warm import schedule_warm_masters_by_id
        schedule_warm_masters_by_id(uncovered_master_ids)

    has_more = page * per_page < total
    return MasterSearchResponse(
        results=results,
        total=total,
        page=page,
        per_page=per_page,
        has_more=has_more,
        next_cursor=page + 1 if has_more else None,
    )


async def get_artist_releases_local(
    db: AsyncSession,
    artist_id: str,
    page: int = 1,
    per_page: int = 50,
):
    """ПЛОСКИЙ список всех изданий артиста из локального дамп-индекса — ноль
    вызовов Discogs. В отличие от get_artist_masters_local (группирует по
    мастеру), возвращает каждый релиз отдельно (все прессы), как live-путь
    discogs.get_artist_releases. None → артиста нет в индексе → live fallback.
    """
    from app.schemas.record import ReleaseSearchResponse, ReleaseSearchResult
    from app.config import get_settings

    if not str(artist_id).isdigit():
        return None

    name_row = (await db.execute(
        text("SELECT name FROM discogs_artists WHERE artist_id = :aid"),
        {"aid": int(artist_id)},
    )).scalar()
    if not name_row:
        return None

    rows = (await db.execute(
        text("""
            SELECT discogs_id, title, label, catalog_norm, country, year,
                   format_type, cover_image_url,
                   COUNT(*) OVER () AS total
            FROM discogs_releases_index
            WHERE artist_ids @> ARRAY[CAST(:aid AS bigint)]
              AND NOT is_unofficial
            ORDER BY year DESC NULLS LAST, discogs_id
            LIMIT :lim OFFSET :off
        """),
        {"aid": int(artist_id), "lim": per_page, "off": (page - 1) * per_page},
    )).mappings().all()

    if not rows and page == 1:
        return None  # артиста нет в индексе → live fallback

    covers_base = get_settings().public_covers_base
    total = rows[0]["total"] if rows else 0
    results = []
    for r in rows:
        # Обложка через собственное зеркало /covers/{id}.jpg (nginx-статика);
        # covers.py резолвит источник по discogs_id. Null → дойдёт фоном.
        cover_url = f"{covers_base}/{r['discogs_id']}.jpg" if r["cover_image_url"] else None
        results.append(ReleaseSearchResult(
            release_id=str(r["discogs_id"]),
            title=r["title"] or "",
            artist=name_row,
            label=r["label"],
            catalog_number=r["catalog_norm"],
            country=r["country"],
            year=r["year"],
            format=r["format_type"],
            cover_image_url=cover_url,
            thumb_image_url=None,
        ))

    # Самолечение обложек непокрытых релизов (CAA → barcode → Discogs budget →
    # iTunes), запись в индекс → следующий заход без заглушек.
    uncovered = [
        r.release_id for r in results
        if not r.cover_image_url and r.release_id.isdigit()
    ]
    if uncovered:
        from app.services.cover_warm import schedule_warm_dump_covers
        schedule_warm_dump_covers(uncovered, discogs_budget=10)

    return ReleaseSearchResponse(
        results=results,
        total=total,
        page=page,
        per_page=per_page,
    )


def _to_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


async def upsert_release_into_index(db: AsyncSession, record_data: dict) -> None:
    """Положить один Discogs-релиз в discogs_releases_index. Идемпотентно.

    record_data — dict из DiscogsService.get_release (ключи id/master_id/artist/
    title/year/country/format/label/barcode/catalog_number/cover_image, плюс
    artist_ids/artist_names — их отдаёт get_release, у прочих вызывающих их
    может не быть).
    Ошибки глотаем (обогащение индекса не должно ронять основной флоу).
    """
    discogs_id = _to_int(record_data.get("id"))
    if discogs_id is None:
        return
    artist = (record_data.get("artist") or "").strip()
    title = (record_data.get("title") or "").strip()
    if not artist or not title:
        return  # artist/title NOT NULL в схеме

    # artist_ids — не украшение: оба запроса дискографии фильтруют
    # `artist_ids @> ARRAY[aid]`, и строка без них невидима на экране артиста
    # навсегда (дампный загрузчик до 2026-08 шёл через ON CONFLICT DO NOTHING и
    # починить её не мог). На 2026-08-14 таких строк было 2 496 из 6 641
    # появившихся после майского дампа — 37% всего свежего.
    raw_ids = record_data.get("artist_ids") or []
    artist_ids = [i for i in (_to_int(x) for x in raw_ids) if i is not None]
    if not artist_ids:
        # Старые вызовы кладут только первый id — лучше он, чем ничего.
        single = _to_int(record_data.get("artist_id"))
        if single is not None:
            artist_ids = [single]

    params = {
        "discogs_id": discogs_id,
        # 0 = «нет мастера» у Discogs → NULL (release-only семантика).
        "master_id": _to_int(record_data.get("master_id")) or None,
        "artist": artist,
        "artist_ids": artist_ids or None,
        "title": title,
        "year": _to_int(record_data.get("year")),
        "country": record_data.get("country"),
        "format_type": record_data.get("format"),
        "label": record_data.get("label"),
        "barcode_norm": normalize_barcode(record_data.get("barcode")),
        "catalog_norm": normalize_catalog(record_data.get("catalog_number")),
        "cover_image_url": record_data.get("cover_image"),
        "dump_version": date.today(),
    }
    try:
        await db.execute(
            text(
                "INSERT INTO discogs_releases_index "
                "(discogs_id, master_id, artist, artist_ids, title, year, country, "
                " format_type, label, barcode_norm, catalog_norm, "
                " cover_image_url, dump_version) "
                # Явный CAST: без него asyncpg не выводит тип пустого/NULL
                # массива и падает на bigint[].
                "VALUES (:discogs_id, :master_id, :artist, "
                " CAST(:artist_ids AS bigint[]), :title, :year, "
                " :country, :format_type, :label, :barcode_norm, :catalog_norm, "
                " :cover_image_url, :dump_version) "
                # Строка уже могла лечь сюда без artist_ids (этот же путь до
                # 2026-08). Дозаписываем, раз уж они теперь есть, — иначе она
                # так и останется невидимой на экране артиста.
                "ON CONFLICT (discogs_id) DO UPDATE SET "
                "  artist_ids = COALESCE(discogs_releases_index.artist_ids, EXCLUDED.artist_ids) "
                "WHERE discogs_releases_index.artist_ids IS NULL "
                "  AND EXCLUDED.artist_ids IS NOT NULL"
            ),
            params,
        )
        # Держим производную таблицу имён в синхроне, чтобы свежий live-артист
        # сразу проходил фильтр поиска (см. filter_artist_names_with_releases).
        #
        # По одному имени на артиста, а НЕ склейку целиком: у релиза с двумя
        # исполнителями `artist` — это "A, B", и такая строка засоряла таблицу
        # именем, которого не существует (в проде осело, например,
        # "boards of canada, boards of canada"), а настоящие A и B в неё не
        # попадали и выпадали из поиска.
        names = record_data.get("artist_names") or [artist]
        for name in names:
            name_norm = (name or "").strip().lower()
            if not name_norm:
                continue
            await db.execute(
                text(
                    "INSERT INTO discogs_artist_names (name_norm) VALUES (:name) "
                    "ON CONFLICT (name_norm) DO NOTHING"
                ),
                {"name": name_norm},
            )
    except Exception as e:  # noqa: BLE001 — индекс-обогащение не критично
        logger.warning("upsert_release_into_index failed for %s: %s", discogs_id, e)
