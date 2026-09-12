"""Маркет, открытый с карточки релиза, обязан показать именно эту пластинку.

Кнопка «В Маркет» читается как обещание. До этой фичи она открывала общую
витрину, где про пластинку, с карточки которой пришли, не было ни строчки, —
и человек, не долиставший до блока офферов, уходил с мыслью, что приложение
соврало. `release_record` сужает выдачу до записи и других изданий её мастера.

Тесты гоняют живой Postgres, потому что все три решения режима — это SQL, и
каждое ломается молча: выдача остаётся правдоподобной, просто отвечает не на
тот вопрос.
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import async_session_maker
from app.main import app
from app.models.record import Record
from app.models.store import Store
from app.models.store_listing import StoreListing

pytestmark = pytest.mark.asyncio


async def _store(slug_hint: str) -> uuid.UUID:
    async with async_session_maker() as db:
        suffix = uuid.uuid4().hex[:8]
        st = Store(
            name=slug_hint, slug=f"{slug_hint}-{suffix}",
            domain=f"{suffix}.example", base_url=f"https://{suffix}.example",
            parser_class="P", is_active=True,
        )
        db.add(st)
        await db.commit()
        return st.id


async def _record(
    *,
    master: str | None,
    title: str,
    fmt: str = "Vinyl",
    fmt_desc: str | None = "LP, Album",
    cover: str | None = "http://x/c.jpg",
) -> uuid.UUID:
    async with async_session_maker() as db:
        rec = Record(
            title=title, artist="Radiohead", source="discogs",
            discogs_id=str(uuid.uuid4().int)[:9], discogs_master_id=master,
            format_type=fmt, format_description=fmt_desc, cover_image_url=cover,
        )
        db.add(rec)
        await db.commit()
        return rec.id


async def _listing(
    store_id: uuid.UUID,
    record_id: uuid.UUID,
    *,
    price: int,
    fmt_raw: str = "LP",
    status: str = "in_stock",
) -> None:
    async with async_session_maker() as db:
        now = datetime.utcnow()
        db.add(StoreListing(
            store_id=store_id, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw=fmt_raw, status=status, price_rub=price,
            matched_record_id=record_id, match_method="fuzzy", matched_at=now,
            last_seen_at=now, first_seen_at=now,
        ))
        await db.commit()


async def _search(**params) -> list[dict]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/market/search", params=params)
    assert res.status_code == 200, res.text
    return res.json()


@pytest_asyncio.fixture
async def shelf():
    """Мастер 777: якорь (винил), переиздание (винил, дешевле), CD. Плюс чужой
    альбом — контроль, что сужение вообще работает."""
    store_a = await _store("a")
    store_b = await _store("b")

    anchor = await _record(master="777", title="OK Computer")
    reissue = await _record(master="777", title="OK Computer 2017")
    cd = await _record(master="777", title="OK Computer CD", fmt="CD", fmt_desc="Album")
    other = await _record(master="888", title="Parklife")

    # Якорь в двух магазинах и дороже переиздания — порядок обязан это пережить.
    await _listing(store_a, anchor, price=5000)
    await _listing(store_b, anchor, price=4500)
    await _listing(store_a, reissue, price=3000, fmt_raw="2xLP")
    await _listing(store_a, cd, price=1000, fmt_raw="CD")
    await _listing(store_a, other, price=2000)

    return {"anchor": anchor, "reissue": reissue, "cd": cd, "other": other}


async def test_scope_keeps_the_release_and_its_pressings_apart(shelf):
    """Обычный дедуп схлопывает издания альбома в одну карточку. Здесь они и
    есть содержание экрана — схлопни их, и показывать станет нечего."""
    items = await _search(release_record=str(shelf["anchor"]))

    assert [it["record_id"] for it in items] == [
        str(shelf["anchor"]), str(shelf["reissue"]),
    ]


async def test_anchor_comes_first_even_when_a_reissue_is_cheaper(shelf):
    """Человек искал глазами свою пластинку: найти её второй — почти не найти."""
    items = await _search(release_record=str(shelf["anchor"]))

    assert items[0]["record_id"] == str(shelf["anchor"])
    assert float(items[0]["min_price_rub"]) > float(items[1]["min_price_rub"])


async def test_anchor_aggregates_all_its_stores(shelf):
    items = await _search(release_record=str(shelf["anchor"]))

    assert items[0]["stores_with_stock"] == 2
    # Минимум по магазинам, а не цена первого попавшегося листинга.
    assert float(items[0]["min_price_rub"]) == 4500


async def test_cd_of_the_same_master_is_not_an_alternative_to_a_vinyl(shelf):
    """Мастер на Discogs объединяет винил, CD и mp3. Человеку, который смотрит
    винил, CD — не «другая версия», а подмена ответа."""
    items = await _search(release_record=str(shelf["anchor"]))

    assert str(shelf["cd"]) not in {it["record_id"] for it in items}


async def test_a_foreign_album_never_leaks_into_the_scope(shelf):
    items = await _search(release_record=str(shelf["anchor"]))

    assert str(shelf["other"]) not in {it["record_id"] for it in items}


async def test_without_scope_the_market_still_dedups_by_master(shelf):
    """Общая витрина не должна пострадать: там разные прессинги одного альбома
    как раз обязаны схлопываться в одну карточку."""
    items = await _search()

    masters = [it["record_id"] for it in items]
    assert len(masters) == len(set(masters))
    # Мастер 777 представлен ровно одной карточкой из трёх своих записей.
    from_777 = {str(shelf["anchor"]), str(shelf["reissue"]), str(shelf["cd"])}
    assert len(from_777 & set(masters)) == 1


async def test_record_without_a_cover_still_shows_in_its_own_scope():
    """На общей витрине карточку без картинки отбрасывают — она там серая дыра.
    В рамках релиза то же правило превращает наличие в «нет в наличии»: экран
    скажет, что пластинки нет, при живом оффере."""
    store = await _store("nocover")
    rec = await _record(master="555", title="No Cover", cover=None)
    await _listing(store, rec, price=1200)

    scoped = await _search(release_record=str(rec))
    assert [it["record_id"] for it in scoped] == [str(rec)]

    # Контроль: на общей витрине её по-прежнему нет — правило не тронуто.
    everywhere = await _search()
    assert str(rec) not in {it["record_id"] for it in everywhere}


async def test_sold_out_anchor_leaves_only_the_other_pressings():
    """Третье состояние экрана: своей версии нет, но альбом достать можно.
    Выдача обязана его различать — плашка над сеткой говорит об этом словами."""
    store = await _store("soldout")
    anchor = await _record(master="666", title="Kid A")
    reissue = await _record(master="666", title="Kid A RE")
    await _listing(store, anchor, price=9000, status="out_of_stock")
    await _listing(store, reissue, price=4000)

    items = await _search(release_record=str(anchor))

    assert [it["record_id"] for it in items] == [str(reissue)]


async def test_store_native_record_has_no_alternatives():
    """У записи без мастера аналогов не существует в принципе — сужение обязано
    остаться на ней одной, а не собрать всё, у чего мастер тоже пуст."""
    store = await _store("native")
    native = await _record(master=None, title="Local Press")
    stranger = await _record(master=None, title="Another Local")
    await _listing(store, native, price=1500)
    await _listing(store, stranger, price=1600)

    items = await _search(release_record=str(native))

    assert [it["record_id"] for it in items] == [str(native)]


async def test_unknown_record_returns_empty_not_the_whole_market():
    """Пустой ответ — это и есть «нет в наличии», его Mobile показывает попапом.
    Отдать вместо него общую витрину значило бы вернуть ровно тот тупик,
    ради которого фича и делалась."""
    store = await _store("ghost")
    alive = await _record(master="444", title="Alive")
    await _listing(store, alive, price=1000)

    assert await _search(release_record=str(uuid.uuid4())) == []


async def test_merged_record_shows_the_offers_of_its_winner():
    """Карточка, которую rematch увёл в дубль, обязана довести до наличия —
    иначе переход отдаёт пустоту при живом оффере."""
    store = await _store("merged")
    winner = await _record(master="333", title="Winner")
    await _listing(store, winner, price=2500)

    async with async_session_maker() as db:
        loser = Record(
            title="Loser", artist="Radiohead", source="discogs",
            discogs_id=str(uuid.uuid4().int)[:9], discogs_master_id="333",
            format_type="Vinyl", format_description="LP, Album",
            merged_into_id=winner,
        )
        db.add(loser)
        await db.commit()
        loser_id = loser.id

    items = await _search(release_record=str(loser_id))

    assert [it["record_id"] for it in items] == [str(winner)]


async def test_stale_listings_do_not_count_as_in_stock():
    """Магазин мог перестать отдавать позицию — 7 дней тишины значит «нет»."""
    store = await _store("stale")
    rec = await _record(master="222", title="Stale")
    async with async_session_maker() as db:
        old = datetime.utcnow() - timedelta(days=30)
        db.add(StoreListing(
            store_id=store, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw="LP", status="in_stock", price_rub=1000,
            matched_record_id=rec, match_method="fuzzy", matched_at=old,
            last_seen_at=old, first_seen_at=old,
        ))
        await db.commit()

    assert await _search(release_record=str(rec)) == []
