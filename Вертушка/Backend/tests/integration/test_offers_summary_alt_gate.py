"""Бейдж «ЕСТЬ АНАЛОГ» обязан обещать ровно то, что покажет Маркет.

Счётчик в вишлисте и выдача Маркета считались по разным правилам: карточка
релиза гейтит носитель и отсекает отключённые магазины, а batch-summary брал
всё подряд по `discogs_master_id`. Человек видел «ЕСТЬ АНАЛОГ», открывал Маркет
и не находил ничего — то есть приложение соврало ему на главном экране.

Живой Postgres здесь обязателен: расхождение целиком в SQL и в том, какие
строки до Python вообще доезжают.
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


async def _store(hint: str, *, active: bool = True) -> uuid.UUID:
    async with async_session_maker() as db:
        suffix = uuid.uuid4().hex[:8]
        st = Store(
            name=hint, slug=f"{hint}-{suffix}",
            domain=f"{suffix}.example", base_url=f"https://{suffix}.example",
            parser_class="P", is_active=active,
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
) -> tuple[uuid.UUID, str]:
    async with async_session_maker() as db:
        discogs_id = str(uuid.uuid4().int)[:9]
        rec = Record(
            title=title, artist="Radiohead", source="discogs",
            discogs_id=discogs_id, discogs_master_id=master,
            format_type=fmt, format_description=fmt_desc,
        )
        db.add(rec)
        await db.commit()
        return rec.id, discogs_id


async def _listing(
    store_id: uuid.UUID,
    record_id: uuid.UUID,
    *,
    price: int = 3000,
    fmt_raw: str = "LP",
    status: str = "in_stock",
    seen_days_ago: int = 0,
) -> None:
    async with async_session_maker() as db:
        now = datetime.utcnow() - timedelta(days=seen_days_ago)
        db.add(StoreListing(
            store_id=store_id, external_id=uuid.uuid4().hex, url="http://x",
            title_raw="T", format_raw=fmt_raw, status=status, price_rub=price,
            matched_record_id=record_id, match_method="fuzzy", matched_at=now,
            last_seen_at=now, first_seen_at=now,
        ))
        await db.commit()


async def _summary(discogs_id: str) -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/records/offers/summary", json={"discogs_ids": [discogs_id]},
        )
    assert res.status_code == 200, res.text
    return res.json().get(discogs_id) or {}


@pytest_asyncio.fixture
async def anchor():
    """Виниловый якорь без единого оффера на себе: всё, что попадёт в
    alt_version_count, придёт от соседей по мастеру."""
    _, discogs_id = await _record(master="9001", title="Kid A")
    return discogs_id


async def test_cd_of_the_same_master_is_not_an_alternative(anchor):
    """Мастер объединяет винил, CD и mp3. Под винилом «аналогом» горел CD."""
    cd, _ = await _record(master="9001", title="Kid A CD", fmt="CD", fmt_desc="Album")
    await _listing(await _store("cd-shop"), cd, fmt_raw="CD")

    assert (await _summary(anchor)).get("alt_version_count", 0) == 0


async def test_digital_of_the_same_master_is_not_an_alternative(anchor):
    """`File, MP3` — формально другой прессинг мастера, по сути не пластинка."""
    digital, _ = await _record(
        master="9001", title="Kid A WEB", fmt="File", fmt_desc="MP3, Album",
    )
    await _listing(await _store("digi"), digital, fmt_raw="MP3")

    assert (await _summary(anchor)).get("alt_version_count", 0) == 0


async def test_vinyl_reissue_is_still_an_alternative(anchor):
    """Гейт не должен съесть то, ради чего бейдж и существует."""
    reissue, _ = await _record(master="9001", title="Kid A 2017")
    await _listing(await _store("vinyl-shop"), reissue, price=4200, fmt_raw="2xLP")

    summary = await _summary(anchor)
    assert summary["alt_version_count"] == 1
    assert float(summary["min_price_alt_rub"]) == 4200


async def test_listing_of_a_disabled_store_does_not_count(anchor):
    """Выдача Маркета фильтрует stores.is_active. Счётчик, который этого не
    делает, обещает офферы магазина, которого в приложении больше нет."""
    reissue, _ = await _record(master="9001", title="Kid A 2017")
    await _listing(await _store("gone", active=False), reissue)

    assert (await _summary(anchor)).get("alt_version_count", 0) == 0


async def test_exact_count_also_ignores_disabled_stores():
    """Тот же гейт на pill «N в наличии»: она считает офферы этой же записи."""
    rec_id, discogs_id = await _record(master="9002", title="Amnesiac")
    await _listing(await _store("gone2", active=False), rec_id)

    assert (await _summary(discogs_id)).get("in_stock_count", 0) == 0


async def test_stale_listing_does_not_count(anchor):
    """Листинг живёт неделю после последнего скана — дальше он не факт."""
    reissue, _ = await _record(master="9001", title="Kid A 2017")
    await _listing(await _store("slow"), reissue, seen_days_ago=30)

    assert (await _summary(anchor)).get("alt_version_count", 0) == 0
