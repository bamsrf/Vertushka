"""is_collectible: две ветки, тристейт и снятие флага.

Пороги правились после замера 09.2026 по всей проде (165 записей с ценой
≥$100). Каждый кейс ниже — реальный релиз оттуда, с живыми числами Discogs:
старая формула (цена ≥$100 + лотов ≤3 + владельцев ≤200) на первых двух давала
метку зря, на третьем и четвёртом — пропускала.
"""
import pytest

from app.api.records import _apply_discogs_release
from app.models.record import Record
from app.services.discogs import DiscogsService as DS


class FakeDB:
    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass

    async def rollback(self):
        pass


def _stats(price: float | None, num_for_sale: int = 1) -> dict:
    """Ответ /marketplace/stats. median_price Discogs не отдаёт — см.
    DiscogsService.collectible_price_usd, поэтому только lowest_price."""
    out: dict = {"num_for_sale": num_for_sale, "blocked_from_sale": False}
    if price is not None:
        out["lowest_price"] = {"value": price, "currency": "USD"}
    return out


# --- спросовая ветка ---------------------------------------------------------

def test_fresh_pressing_with_one_greedy_seller_is_not_collectible():
    # Сироткин — Мрамор (37401393): один лот за $110, но желающих 2 на 20 владельцев
    assert DS.compute_is_collectible(_stats(110.47), have=20, want=2) is False


def test_expensive_repress_without_demand_is_not_collectible():
    # FBC/VHOOR — Baile (37200081): $107 и 4 лота, но want втрое меньше have
    assert DS.compute_is_collectible(_stats(107.84, num_for_sale=4), have=142, want=51) is False


def test_hunted_release_is_collectible_even_on_a_single_lot():
    # Фирюза (2240385): один лот, 66 владельцев, 1114 желающих
    assert DS.compute_is_collectible(_stats(1614.86), have=66, want=1114) is True


def test_many_owners_do_not_block_demand_branch():
    # Eminem — Infinite (have=279 > старого порога 200), want/have = 11
    assert DS.compute_is_collectible(_stats(7500.0), have=279, want=3080) is True


def test_many_lots_do_not_block_demand_branch():
    # Ryo Fukui — Scenery, японский оригинал: 10 лотов, старая формула резала
    assert DS.compute_is_collectible(_stats(880.0, num_for_sale=10), have=414, want=5733) is True


def test_tiny_sample_does_not_pass_noise_floor():
    # have=3 / want=11: отношение 3.7, но абсолютных желающих меньше порога
    assert DS.compute_is_collectible(_stats(116.28), have=3, want=11) is False


def test_demand_without_price_threshold_is_not_collectible():
    # Спрос есть, но пластинка дешёвая — это «Популярно», не «Коллекционка»
    assert DS.compute_is_collectible(_stats(12.0), have=30, want=200) is False


# --- ценовая ветка -----------------------------------------------------------

def test_expensive_limited_edition_with_settled_price_is_collectible():
    # Daft Punk — Discovery, японский репресс (32560179): want/have=1.26,
    # спросовая ветка не берёт, но $581 при 1622 владельцах — цена устоялась
    assert DS.compute_is_collectible(_stats(581.38, num_for_sale=15), have=1622, want=2039) is True


def test_high_ask_from_a_lone_seller_does_not_trigger_price_branch():
    # $2500 при 12 владельцах — это не цена, а фантазия одного продавца.
    # Ценовая ветка требует have ≥ 100, поэтому молчит, и без спроса вердикт «нет».
    assert DS.compute_is_collectible(_stats(2500.0), have=12, want=5) is False


# --- тристейт: «не знаем» ≠ «не редкая» --------------------------------------

def test_no_price_with_demand_is_unknown():
    # Ryo Fukui — Scenery (13941669): 0 лотов, 2476 желающих. Вердикта нет.
    assert DS.compute_is_collectible(_stats(None, num_for_sale=0), have=33, want=544) is None


def test_no_price_with_many_owners_is_unknown():
    # have ≥ 100 — ценовая ветка была бы разрешима, но цены нет
    assert DS.compute_is_collectible(None, have=1622, want=100) is None


def test_no_price_and_no_chance_is_a_definite_no():
    # Ни спроса, ни базы владельцев — твёрдое «нет», сеть больше не нужна
    assert DS.compute_is_collectible(None, have=20, want=2) is False


# --- донос до колонки --------------------------------------------------------

def _record(**kwargs) -> Record:
    defaults = dict(
        discogs_id="123", title="T", artist="A", source="discogs",
        cover_image_url="http://example/c.jpg", barcode=None,
        is_limited=False, is_collectible=False, is_hot=False,
    )
    defaults.update(kwargs)
    return Record(**defaults)


@pytest.mark.asyncio
async def test_flag_is_cleared_when_release_stops_qualifying():
    rec = _record(is_collectible=True)
    await _apply_discogs_release(rec, {"is_collectible": False}, FakeDB())
    assert rec.is_collectible is False


@pytest.mark.asyncio
async def test_unknown_verdict_leaves_flag_untouched():
    rec = _record(is_collectible=True)
    await _apply_discogs_release(rec, {"is_collectible": None}, FakeDB())
    assert rec.is_collectible is True


@pytest.mark.asyncio
async def test_limited_still_only_ratchets_up():
    rec = _record(is_limited=True)
    await _apply_discogs_release(rec, {"is_limited": False}, FakeDB())
    assert rec.is_limited is True


# --- SQL скрипта пересчёта ---------------------------------------------------

def test_recalc_sql_binds_every_parameter():
    """Плейсхолдеры в UPDATE'ах пересчёта действительно распознаются.

    Первый прогон с --apply записал ноль изменений: в условии стоял
    постфиксный каст `:id::bigint`, и SQLAlchemy не считал `:id` параметром
    вовсе — запрос уезжал в Postgres с двоеточиями и падал синтаксисом. Ошибка
    проявлялась только на живой базе, поэтому проверяем компиляцию здесь.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy import text
    from sqlalchemy.dialects import postgresql
    from scripts.recalc_collectible import SQL_SET_INDEX, SQL_SET_RECORD

    for sql, expected in ((SQL_SET_RECORD, {"v", "id"}), (SQL_SET_INDEX, {"v", "did"})):
        compiled = text(sql).compile(dialect=postgresql.dialect())
        assert set(compiled.params) == expected, sql
        assert ":" not in compiled.string, f"нераспознанный плейсхолдер: {compiled.string}"
