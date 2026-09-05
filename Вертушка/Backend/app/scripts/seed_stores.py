"""Идемпотентный сидинг магазинов винила в таблицу `stores`.

Использование:
  python -m app.scripts.seed_stores                # посеять все из STORES
  python -m app.scripts.seed_stores --slug=<slug>  # одну запись
  python -m app.scripts.seed_stores --list         # просто показать что засеется

Чтобы добавить новый магазин — добавь словарь в STORES ниже и перезапусти.
"""
import argparse
import asyncio
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from app.database import async_session_maker, close_db
from app.models.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("seed_stores")


# ---- Список магазинов для посева -------------------------------------- #
# parser_class должен совпадать со slug в @register_parser(...) внутри
# app/services/scrapers/shops/<file>.py

STORES: list[dict] = [
    {
        "slug": "korobkavinyla",
        "name": "Коробка Винила",
        "domain": "korobkavinyla.ru",
        "base_url": "https://korobkavinyla.ru",
        "parser_class": "korobkavinyla",
        "logo_url": None,
        "rating": Decimal("4.5"),
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,  # пока без партнёрки
    },
    {
        "slug": "plastinka_com",
        "name": "Plastinka.com",
        "domain": "plastinka.com",
        "base_url": "https://plastinka.com",
        "parser_class": "plastinka_com",
        "logo_url": None,
        "rating": Decimal("4.7"),  # крупный СПб-магазин, много отзывов
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("450.00"),
        "affiliate_program": None,
    },
    {
        "slug": "vinyl_ru",
        "name": "Vinyl.ru",
        "domain": "vinyl.ru",
        "base_url": "https://vinyl.ru",
        "parser_class": "vinyl_ru",
        "logo_url": None,
        "rating": Decimal("4.4"),  # большой Bitrix-каталог 64k+ товаров, все форматы
        # Выключен 09.08: sitemap-обход 36 часов не влезает в ночное окно;
        # включать только после перевода на YML/инкремент
        # (см. docs/plans/MARKET_STORES_SCALING.md §2, §7a). Полный прогон
        # сидинга НЕ должен молча реанимировать магазин — поэтому False.
        "is_active": False,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
    {
        "slug": "stoprobotvinyl",
        "name": "Stoprobot Vinyl",
        "domain": "stoprobotvinyl.ru",
        "base_url": "https://stoprobotvinyl.ru",
        "parser_class": "stoprobotvinyl",
        "logo_url": None,
        "rating": Decimal("4.6"),  # ~8.9k товаров, только винил, нишевые лейблы/raras
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
    {
        "slug": "found",
        "name": "Found",
        "domain": "pizza.foundmoscow.com",
        "base_url": "https://pizza.foundmoscow.com",
        "parser_class": "found",
        "logo_url": None,  # Mobile рендерит локальный assets/found.png по slug
        "rating": Decimal("4.5"),  # Tilda store-API, ~1.6k товаров, винил/CD
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
    {
        "slug": "doctorhead",
        "name": "Dr.Head",
        "domain": "doctorhead.ru",
        "base_url": "https://doctorhead.ru",
        "parser_class": "doctorhead",
        "logo_url": None,  # Mobile рендерит локальный assets/doctorhead.png по slug
        "rating": Decimal("4.6"),  # федеральная сеть аудио-магазинов, раздел «Музыка»
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
    {
        # Заведён в прод-БД руками 2026-08-09 мимо этого скрипта; значения
        # ниже сняты с прода 2026-08-23. rating=0 и avg_shipping_rub=None на
        # проде так и не заполнены — при простановке реальных значений менять
        # здесь, прод подтянется прогоном сидинга.
        "slug": "skifmusic",
        "name": "Скифмьюзик",
        "domain": "skifmusic.ru",
        "base_url": "https://skifmusic.ru",
        "parser_class": "skifmusic",
        "logo_url": None,  # Mobile рендерит локальный assets/skifmusic.png по slug
        "rating": Decimal("0.00"),
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": None,
        "affiliate_program": None,
    },
    {
        # Заведён в прод-БД руками 2026-08-11 мимо этого скрипта; значения
        # ниже сняты с прода 2026-08-23. rating=0 и avg_shipping_rub=None на
        # проде так и не заполнены — при простановке реальных значений менять
        # здесь, прод подтянется прогоном сидинга.
        "slug": "rotaryrecords",
        "name": "Rotary Records",
        "domain": "rotaryrecords.store",
        "base_url": "https://rotaryrecords.store",
        "parser_class": "rotaryrecords",
        "logo_url": None,  # Mobile рендерит локальный assets/rotaryrecords.png по slug
        "rating": Decimal("0.00"),
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": None,
        "affiliate_program": None,
    },
    {
        "slug": "long_play",
        "name": "Long Play",
        "domain": "long-play.ru",
        "base_url": "https://long-play.ru",
        "parser_class": "long_play",
        "logo_url": None,  # Mobile рендерит локальный assets/long_play.png по slug
        "rating": Decimal("4.5"),  # б/у винил, ~2.6k позиций, грейды по Discogs
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
    {
        "slug": "vinylhouse",
        "name": "Дом Винила",
        "domain": "vinylhouse.ru",
        "base_url": "https://vinylhouse.ru",
        "parser_class": "vinylhouse",
        "logo_url": None,  # Mobile рендерит локальный assets/vinylhouse.png по slug
        "rating": Decimal("4.6"),  # б/у оригиналы, СПб (Мойка), ~10k позиций, грейды на стр. товара
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("450.00"),
        "affiliate_program": None,
    },
    {
        "slug": "kultura",
        "name": "Kultura Record Store",
        "domain": "kulturarecordstore.ru",
        "base_url": "https://kulturarecordstore.ru",
        "parser_class": "kultura",
        "logo_url": None,  # Mobile рендерит локальный assets/kultura.png по slug
        "rating": Decimal("4.6"),  # Tilda store-API, ~4.3k, электроника/эксперимент/хип-хоп/джаз, есть катномера
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
    {
        "slug": "vinylfamily",
        "name": "Vinyl Family",
        "domain": "vinylfamily.shop",
        "base_url": "https://vinylfamily.shop",
        "parser_class": "vinylfamily",
        "logo_url": None,  # Mobile рендерит локальный assets/vinylfamily.png по slug
        "rating": Decimal("4.4"),  # Tilda store-API, ~1.4k, новьё метал/рок/электроника, катномер у 100%
        "is_active": True,
        "requires_browser": False,
        "avg_shipping_rub": Decimal("400.00"),
        "affiliate_program": None,
    },
]


async def seed_one(payload: dict) -> str:
    """UPSERT по slug. Возвращает 'created' / 'updated' / 'unchanged'."""
    async with async_session_maker() as db:
        existing = await db.execute(select(Store).where(Store.slug == payload["slug"]))
        store = existing.scalar_one_or_none()

        if store is None:
            store = Store(**payload)
            db.add(store)
            await db.commit()
            return "created"

        # Обновляем безопасные поля; `last_successful_scrape_at` не трогаем.
        changed = False
        for key in ("name", "domain", "base_url", "parser_class", "logo_url",
                    "rating", "is_active", "requires_browser",
                    "avg_shipping_rub", "affiliate_program"):
            if key in payload and getattr(store, key) != payload[key]:
                setattr(store, key, payload[key])
                changed = True
        if changed:
            store.updated_at = datetime.utcnow()
            await db.commit()
            return "updated"
        return "unchanged"


async def main_async(args: argparse.Namespace) -> None:
    targets = (
        [s for s in STORES if s["slug"] == args.slug] if args.slug else STORES
    )
    if not targets:
        logger.error("Нет магазина со slug=%s в STORES", args.slug)
        return

    if args.list:
        for s in targets:
            print(f"  • {s['slug']:25s} → {s['parser_class']:20s} [{'CF' if s.get('requires_browser') else 'http'}]")
        return

    for payload in targets:
        try:
            status = await seed_one(payload)
            logger.info("%s: %s", payload["slug"], status)
        except Exception:
            logger.exception("seed failed for %s", payload["slug"])

    await close_db()


def main() -> None:
    p = argparse.ArgumentParser(description="Seed Store records")
    p.add_argument("--slug", help="посеять только один магазин")
    p.add_argument("--list", action="store_true", help="не сеять — просто показать")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
