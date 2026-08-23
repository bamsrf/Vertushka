"""Скан по штрихкоду отдаёт все издания альбома, а не один пресс.

Регрессия: локальный ярус /records/scan/barcode возвращал ровно одну запись
(limit(1) — хотфикс от MultipleResultsFound) и коротко замыкал каскад — юзер
сканировал пластинку и видел единственное издание одного года, хотя на Discogs
у мастера десятки версий.

Теперь эндпоинт: собирает ВСЕ точные совпадения по коду (локальная БД +
dump-индекс, с дедупликацией по discogs_id), помечает их is_exact_match=True,
затем через master_id из dump-индекса добирает другие виниловые издания того
же мастера (is_exact_match=False, после точных).
"""
from types import SimpleNamespace
from uuid import uuid4

import app.api.records as records_api
from app.api.records import scan_barcode


class FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        rows = self._rows
        return SimpleNamespace(all=lambda: rows, first=lambda: rows[0] if rows else None)

    def mappings(self):
        rows = self._rows
        return SimpleNamespace(all=lambda: rows)

    def scalar(self):
        return self._scalar


class FakeSession:
    """Отдаёт заранее заготовленные результаты по порядку вызовов execute."""

    def __init__(self, *results):
        self._results = list(results)
        self.queries = []

    async def execute(self, query, *args, **kwargs):
        self.queries.append(str(query))
        return FakeResult(**self._results.pop(0))


def make_local_record(discogs_id="111", year=1977):
    return SimpleNamespace(
        id=uuid4(),
        discogs_id=discogs_id,
        title="Rumours",
        artist="Fleetwood Mac",
        label="Warner",
        year=year,
        country="US",
        cover_image_url="https://covers/111.jpg",
        thumb_image_url=None,
        format_type="Vinyl, LP",
    )


def dump_row(discogs_id, year, master_id=None, fmt="Vinyl, LP"):
    return {
        "discogs_id": discogs_id,
        "master_id": master_id,
        "artist": "Fleetwood Mac",
        "title": "Rumours",
        "year": year,
        "country": "US",
        "format_type": fmt,
        "label": "Warner",
        "cover_image_url": None,
    }


def _mute_cover_warm(monkeypatch):
    from app.services import cover_warm

    async def _noop_inline(ids, timeout):
        return None

    monkeypatch.setattr(cover_warm, "schedule_warm_dump_covers", lambda ids: None)
    monkeypatch.setattr(cover_warm, "warm_dump_covers_inline", _noop_inline)


async def test_scan_returns_exact_matches_plus_master_siblings(monkeypatch):
    """Локальная запись + dump-дубль не замыкают каскад: приходят сиблинги мастера."""
    _mute_cover_warm(monkeypatch)
    db = FakeSession(
        # 1. локальная БД: один известный пресс
        {"rows": [make_local_record("111")]},
        # 2. dump по barcode_norm: тот же релиз (дедуп) — несёт master_id
        {"rows": [dump_row("111", 1977, master_id=555)]},
        # 3. сиблинги мастера: сам релиз (дедуп) + два других года
        {"rows": [
            dump_row("111", 1977),
            dump_row("222", 1984),
            dump_row("333", 2011),
        ]},
        # 4. перечитка обложек после инлайн-прогрева: 222 успел прогреться
        {"rows": [{"discogs_id": "222", "cover_image_url": "https://caa/222.jpg"}]},
    )

    results = await scan_barcode(barcode="0093652", current_user=None, db=db)

    assert [r.discogs_id for r in results] == ["111", "222", "333"]
    assert [r.is_exact_match for r in results] == [True, False, False]
    # Обложка, дописанная прогревом в индекс, вернулась прямо в ответе
    assert results[1].cover_image_url == "https://caa/222.jpg"
    assert results[2].cover_image_url is None
    # master_id взят из dump-строки — отдельный доисковый запрос не нужен
    assert len(db.queries) == 4
    assert "master_id = :mid" in db.queries[2]


async def test_scan_returns_all_records_sharing_barcode(monkeypatch):
    """Не-merged локальные дубли одного кода приходят все, а не первый попавшийся."""
    _mute_cover_warm(monkeypatch)
    db = FakeSession(
        {"rows": [make_local_record("111"), make_local_record("777", year=1984)]},
        {"rows": []},          # dump по barcode пуст
        {"scalar": None},      # master_id не нашёлся по discogs_id точных
    )

    results = await scan_barcode(barcode="0093652", current_user=None, db=db)

    assert [r.discogs_id for r in results] == ["111", "777"]
    assert all(r.is_exact_match for r in results)


async def test_scan_empty_falls_back_to_discogs_and_marks_exact(monkeypatch):
    """Пустая локалка → Discogs API; его результаты — точные совпадения."""
    _mute_cover_warm(monkeypatch)
    from app.schemas.record import RecordSearchResult

    api_result = RecordSearchResult(
        discogs_id="999", title="Rumours", artist="Fleetwood Mac",
        label=None, year=1977, country=None,
        cover_image_url=None, thumb_image_url=None, format_type="Vinyl",
    )

    class FakeDiscogs:
        async def search_by_barcode(self, barcode):
            return [api_result]

    monkeypatch.setattr(records_api, "DiscogsService", FakeDiscogs)
    db = FakeSession(
        {"rows": []},                       # локальная БД пуста
        {"rows": []},                       # dump по barcode пуст
        {"scalar": 555},                    # master_id найден по discogs_id 999
        {"rows": [dump_row("222", 1984)]},  # сиблинги мастера
        {"rows": []},                       # перечитка обложек: ничего не успело
    )

    results = await scan_barcode(barcode="0093652", current_user=None, db=db)

    assert [r.discogs_id for r in results] == ["999", "222"]
    assert [r.is_exact_match for r in results] == [True, False]


async def test_scan_nothing_found_returns_empty(monkeypatch):
    """Полный промах остаётся graceful: [] вместо 503."""
    _mute_cover_warm(monkeypatch)

    class FakeDiscogs:
        async def search_by_barcode(self, barcode):
            raise TimeoutError

    monkeypatch.setattr(records_api, "DiscogsService", FakeDiscogs)
    db = FakeSession({"rows": []}, {"rows": []})

    assert await scan_barcode(barcode="0093652", current_user=None, db=db) == []


async def test_inline_warm_times_out_but_task_survives(monkeypatch):
    """Бюджет времени истёк → отдаём ответ, но прогрев НЕ отменяется."""
    import asyncio

    from app.services import cover_warm

    done = asyncio.Event()

    async def slow_warm(ids, budget=None):
        await asyncio.sleep(0.2)
        done.set()

    monkeypatch.setattr(cover_warm, "warm_dump_covers", slow_warm)

    await cover_warm.warm_dump_covers_inline(["1"], timeout=0.05)
    assert not done.is_set()  # вернулись раньше, чем прогрев закончился
    await asyncio.wait_for(done.wait(), timeout=1)  # но задача дожила в фоне


def test_siblings_query_is_vinyl_only():
    """Dump-индекс хранит все форматы мастера — CD/кассеты в скан не попадают."""
    import inspect

    src = inspect.getsource(records_api.scan_barcode)
    assert "format_type LIKE 'Vinyl%'" in src
