"""Продюсер падений цены обязан брать привязку из store_listings, а не из денорма.

Что здесь ловится. `listing_price_history.record_id` заполняется в
`_upsert_listing` значением `matched_record_id` НА МОМЕНТ снятия снапшота.
Матчинг листингов — отдельная часовая задача (`hourly_match_unmatched`), и
`listing_matcher` историю не досыпает: в нём нет ни одного обращения к
ListingPriceHistory. Значит всё, что снято до матча, лежит с record_id=NULL.

Пока `_run_price_drop` фильтровал по денорму, ломалось два места:

1. `ranked` вырезал до-матчевые строки ДО вычисления окна, поэтому у первого
   снапшота после привязки не оказывалось предшественника в партиции LAG:
   prev_price=NULL → строка гибла на `prev_price.is_not(None)`. Первое падение
   цены на свежепривязанном листинге не рождало ни одного wishlist_price_drop.
2. `previous_low` считался по половине истории, и «дешевле ещё не было»
   (is_all_time_low — пробивает push даже без порога) уезжало в пуш на цене,
   которую уже били раньше.

Тот же денорм фильтровал базу относительного порога (`baseline_prices`) —
из-за MIN_BASELINE_DAYS свежая пластинка оставалась без базы, и режим
«дешевле обычного» молча сваливался на price_threshold_rub.

Живой БД у тестов нет — перехватываем сами statement'ы и смотрим на скомпи-
лированный SQL: джойн есть, фильтра по денорму нет.
"""
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.services.radar_threshold import baseline_prices
from app.tasks import notification_tasks
from app.tasks.notification_tasks import MIN_DROP_PCT, _run_price_drop


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._rows)


class _FakeBind:
    dialect = postgresql.dialect()


class CapturingSession:
    """Стаб AsyncSession: запоминает statement'ы и отдаёт заготовленные строки."""

    def __init__(self, *result_rows):
        self.statements = []
        self._queue = [list(r) for r in result_rows]
        self.committed = False

    async def execute(self, statement, *_args, **_kwargs):
        self.statements.append(statement)
        rows = self._queue.pop(0) if self._queue else []
        return _FakeResult(rows)

    def get_bind(self):
        return _FakeBind()

    async def commit(self):
        self.committed = True


def _sql(statement, *, literal_binds: bool = False) -> str:
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": literal_binds},
    )
    return str(compiled)


def _drop_session(record_id):
    """Сессия, доводящая _run_price_drop до обоих интересных запросов.

    Первый execute — выборка падений (иначе ранний return), второй —
    previous_low, третий — wishlist_items: пустой, дальше по коду нам не надо.
    """
    return CapturingSession([(record_id, 5000, 3352)], [], [])


async def test_drop_query_joins_store_listings_for_current_match():
    record_id = uuid4()
    db = _drop_session(record_id)
    await _run_price_drop(db)

    sql = _sql(db.statements[0])
    assert "store_listings" in sql, "привязка должна браться джойном"
    assert "matched_record_id" in sql, "источник истины — текущий матч листинга"


async def test_drop_query_does_not_filter_by_denormalized_record_id():
    """Регрессия: возврат к денорму снова спрячет до-матчевые снапшоты."""
    db = _drop_session(uuid4())
    await _run_price_drop(db)

    sql = _sql(db.statements[0])
    assert "listing_price_history.record_id" not in sql, (
        "денорм заполняется на момент снапшота и отстаёт от матча — "
        "фильтровать по нему значит терять падения на свежих привязках"
    )


async def test_drop_query_takes_record_identity_from_the_join():
    """Кому слать — решает джойн: LAG партиционирован по листингу, не по записи.

    Если record_id продолжит приезжать из денорма, продюсер будет уведомлять
    по устаревшей привязке (или молчать на NULL) при том же наборе строк.
    """
    db = _drop_session(uuid4())
    await _run_price_drop(db)

    sql = _sql(db.statements[0])
    assert "store_listings.matched_record_id AS record_id" in sql
    assert "PARTITION BY listing_price_history.listing_id" in sql, (
        "окно по-прежнему считается внутри листинга — джойн 1:1 его не трогает"
    )


async def test_drop_query_keeps_min_drop_pct_and_in_stock_filters():
    """Джойн не должен был растерять прежние условия отбора падения."""
    db = _drop_session(uuid4())
    await _run_price_drop(db)

    sql = _sql(db.statements[0], literal_binds=True)
    assert str(1 - MIN_DROP_PCT) in sql, "порог падения 10% на месте"
    assert "prev_price IS NOT NULL" in sql
    assert "status" in sql and "captured_at" in sql


async def test_previous_low_joins_store_listings():
    """Всё-время-минимум считается по ПОЛНОЙ истории, иначе all_time_low врёт.

    is_all_time_low пробивает push даже watched-айтемам без порога, так что
    неполная история здесь дороже, чем на графике.
    """
    db = _drop_session(uuid4())
    await _run_price_drop(db)

    sql = _sql(db.statements[1])
    assert "store_listings" in sql and "matched_record_id" in sql
    assert "listing_price_history.record_id" not in sql
    assert "min(listing_price_history.price_rub)" in sql


async def test_baseline_prices_joins_store_listings():
    """База относительного порога — из того же источника, что и график.

    Иначе «дешевле обычного» разъезжается с картинкой в шторке цены, а
    MIN_BASELINE_DAYS не набирается и порог молча сваливается на рубли.
    """
    db = CapturingSession([])
    await baseline_prices(db, [uuid4()])

    sql = _sql(db.statements[0])
    assert "store_listings" in sql and "matched_record_id" in sql
    assert "listing_price_history.record_id" not in sql


async def test_price_drop_dedup_keys_stay_per_record(monkeypatch):
    """Больше найденных падений не значит больше пушей.

    Нить дедупится по dedup_key (одна живая строка на пластинку — повторное
    падение бампает, а не шлёт второй push), а сам push — часовым freq-cap по
    cap_key. Оба ключа обязаны остаться пер-записными: сорвись это в пер-
    листинговое, один и тот же релиз в девяти магазинах дал бы девять пушей.
    """
    record_id = uuid4()
    record = SimpleNamespace(
        id=record_id, title="Song Machine", artist="Gorillaz", cover_image_url=None
    )
    item = SimpleNamespace(
        record_id=record_id,
        record=record,
        notify_mode="subscribed",
        price_threshold_rub=None,
        threshold_pct=None,
        wishlist=SimpleNamespace(user_id=uuid4()),
    )

    calls = []

    async def fake_upsert(_db, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id=uuid4()), True

    async def fake_radar_event(*_args, **_kwargs):
        return None

    async def fake_baselines(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(notification_tasks, "upsert_notification", fake_upsert)
    monkeypatch.setattr(notification_tasks, "record_radar_event", fake_radar_event)
    monkeypatch.setattr(notification_tasks, "baseline_prices", fake_baselines)

    # Два падения по одной пластинке в разных магазинах + прошлый минимум.
    db = CapturingSession(
        [(record_id, 5000, 3800), (record_id, 4200, 3352)],
        [(record_id, 3000)],
        [item],
    )
    await _run_price_drop(db)

    assert len(calls) == 1, "на пластинку — одна нить, а не одна на листинг"
    assert calls[0]["dedup_key"] == f"wishlist_price_drop:{record_id}"
    assert calls[0]["push_cap_key"] == f"wl_drop:{record_id}"
    # Берём максимальное падение: самый низкий new и его же old.
    assert calls[0]["data"]["new_price_rub"] == 3352.0
    assert calls[0]["data"]["old_price_rub"] == 4200.0
    # Прошлый минимум 3000 < 3352 — «дешевле не было» заявлять не на чем.
    assert calls[0]["data"]["all_time_low"] is False
