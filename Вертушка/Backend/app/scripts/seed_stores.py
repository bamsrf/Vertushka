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
        "is_active": True,
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
