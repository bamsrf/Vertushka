"""Baseline: таблицы вишлиста и подарков + UNIQUE-индекс от двойной брони.

Исторически схему бутстрапил `Base.metadata.create_all` на старте приложения
(app/database.py::init_db). Он давно отключён — схемой управляет только alembic.
Но в цепочке миграций никто и никогда не СОЗДАВАЛ таблицы wishlists,
wishlist_items, wishlist_folders, wishlist_folder_items, gift_bookings — их
всегда лепил create_all, а последующие миграции лишь делали ALTER поверх.

Отдельно важен UNIQUE-индекс `ix_gift_bookings_wishlist_item_id`: именно он —
единственный барьер против гонки, когда два дарителя параллельно бронируют один
пункт вишлиста (Python-проверка `if item.gift_booking` ловит только
последовательный случай; параллельный ловится через IntegrityError на этом
индексе, см. app/api/gifts.py::book_gift). На проде индекс есть, но его
существование ничем в коде не гарантировалось и не покрывалось миграцией —
скрытая хрупкость.

Эта миграция закрывает обе дыры ИДЕМПОТЕНТНО:

  1. Создаёт недостающие таблицы из актуального Base.metadata (checkfirst=True —
     существующие таблицы не трогаются). На проде и в тестовом conftest, где
     таблицы уже есть, это чистый no-op.
  2. Отдельно и безусловно доводит до наличия сам UNIQUE-индекс
     `CREATE UNIQUE INDEX IF NOT EXISTS ... (wishlist_item_id)`. Имя совпадает с
     тем, что генерит модель (`unique=True, index=True`), поэтому на проде IF NOT
     EXISTS — no-op, а таблица, которая почему-то осталась без индекса, его
     получает. Обычный UNIQUE на nullable-колонке в Postgres допускает много
     NULL — ровно то, что нужно: отменённые/завершённые брони (wishlist_item_id
     обнулён) не конфликтуют, а активная бронь на пункт может быть только одна.

downgrade — no-op намеренно: таблицы существовали до этой миграции (их создавал
create_all), «откатить» их значило бы снести живые данные вишлистов и подарков.
Тот же принцип, что в 20260819_legacy_startup_ddl.

Revision ID: 20260820_wishlist_gift_baseline
Revises: 20260819_startup_ddl
Create Date: 2026-08-20
"""
from alembic import op

# Модели наполняют Base.metadata. env.py и так делает `from app.models import *`,
# но импортируем явно — чтобы миграция была самодостаточной в любом контексте.
import app.models  # noqa: F401
from app.database import Base

revision = "20260820_wishlist_gift_baseline"
down_revision = "20260819_startup_ddl"
branch_labels = None
depends_on = None

# Порядок важен: каждая таблица создаётся вместе со своими FK, поэтому её
# зависимости уже должны существовать (users/records создаёт более ранний
# бутстрап, здесь мы опираемся на них). Внутри списка — топологический порядок:
# wishlists ← wishlist_items ← (wishlist_folders, wishlist_folder_items),
# gift_bookings зависит от wishlist_items.
_TABLES_IN_ORDER = [
    "wishlists",
    "wishlist_items",
    "wishlist_folders",
    "wishlist_folder_items",
    "gift_bookings",
]

# Имя обязано совпадать с индексом, который генерит модель GiftBooking
# (mapped_column(..., unique=True, index=True) → ix_<table>_<column>), иначе
# IF NOT EXISTS не распознает уже существующий на проде индекс и попытается
# создать дубль.
_UNIQUE_INDEX_NAME = "ix_gift_bookings_wishlist_item_id"


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Создаём только недостающие таблицы. checkfirst=True → существующие
    #    (прод, conftest-create_all) пропускаются целиком, никаких ALTER.
    for name in _TABLES_IN_ORDER:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)

    # 2. Гарантируем сам барьер от гонки — даже если таблица уже была, но без
    #    индекса. На проде, где индекс есть, IF NOT EXISTS делает это no-op'ом.
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_UNIQUE_INDEX_NAME} "
        "ON gift_bookings (wishlist_item_id)"
    )


def downgrade() -> None:
    # См. докстринг: таблицы старше миграции, откатывать нечего — иначе снесём
    # чужие данные.
    pass
