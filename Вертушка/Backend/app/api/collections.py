"""
API для работы с коллекциями
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.models.collection import Collection, CollectionItem
from app.api.auth import get_current_user
from app.config import get_settings
from app.services.exchange import get_usd_rub_rate
from app.services.cover_storage import ensure_cover_cached
from app.services.pricing import PricingParams, estimate_rub


def _record_rub(record: Record, usd_rub: float, params: PricingParams) -> float:
    """Считает цену в рублях для записи через компонентную формулу."""
    if not record.estimated_price_min:
        return 0.0
    return estimate_rub(
        float(record.estimated_price_min),
        record.country,
        usd_rub,
        params,
        format_type=record.format_type,
        format_description=record.format_description,
        discogs_data=record.discogs_data,
    )


from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionItemCreate,
    CollectionItemUpdate,
    CollectionItemResponse,
    CollectionWithItems,
    CollectionStats,
    GiftMatchInfo,
)
from app.schemas.record import RecordBrief


def _item_record_brief(item: CollectionItem) -> "Record | RecordBrief":
    """
    Обложка элемента коллекции с учётом своего фото юзера.

    Если у item есть UserRecordPhoto с is_primary=True — отдаём RecordBrief с
    cover_url, перекрытым этим фото (юзер сфоткал свою пластинку и хочет видеть
    её, а не обложку Discogs). Иначе возвращаем ORM-запись как есть (Pydantic
    сериализует через from_attributes).

    Требует, чтобы item.user_photos был загружен (selectinload).
    """
    photos = getattr(item, "user_photos", None) or []
    primary = next((p for p in photos if p.is_primary), None)
    if not primary:
        return item.record
    rb = RecordBrief.model_validate(item.record)
    rb.cover_url = f"/uploads/{primary.photo_path}"
    return rb


router = APIRouter()


@router.post("/recalculate-prices")
async def recalculate_prices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Пересчёт цен: перезапрашивает lowest_price из Discogs (в USD) и пересчитывает рубли.
    Ограничен до 50 уникальных записей за вызов. Для полного обновления используйте
    фоновую задачу update_prices_batch (ежедневно в 4:00).
    """
    from app.services.discogs import DiscogsService

    MAX_RECORDS = 50

    # Элементы коллекций ТЕКУЩЕГО пользователя
    items_result = await db.execute(
        select(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == current_user.id)
        .options(selectinload(CollectionItem.record))
    )
    items = items_result.scalars().all()

    if not items:
        return {"updated": 0, "total": 0}

    settings = get_settings()
    usd_rub = await get_usd_rub_rate()
    discogs = DiscogsService()

    # Группируем по discogs_id, лимитируем до MAX_RECORDS
    records_map: dict[str, Record] = {}
    for item in items:
        if item.record and item.record.discogs_id:
            records_map[item.record.discogs_id] = item.record
            if len(records_map) >= MAX_RECORDS:
                break

    # Перезапрашиваем цены из Discogs (в USD)
    updated_records = 0
    for discogs_id, record in records_map.items():
        try:
            stats = await discogs._get_price_stats(discogs_id)
            if stats:
                lowest = stats.get("lowest_price", {}).get("value")
                if lowest is not None:
                    record.estimated_price_min = lowest
                    record.price_currency = "USD"
                    updated_records += 1
        except Exception:
            continue

    # Пересчитываем рубли во всех CollectionItem
    params = PricingParams.from_settings(settings)
    updated_items = 0
    for item in items:
        record = item.record
        if record and record.estimated_price_min:
            item.estimated_price_rub = _record_rub(record, usd_rub, params)
            updated_items += 1
        else:
            item.estimated_price_rub = None

    await db.commit()

    return {
        "updated_records": updated_records,
        "updated_items": updated_items,
        "total_items": len(items),
        "max_records_per_call": MAX_RECORDS,
        "usd_rub_rate": usd_rub,
    }


@router.get("/owned-ids")
async def get_owned_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Все идентификаторы пластинок, которые есть у пользователя — во всех его
    коллекциях (основная + папки). Лёгкий запрос (только две колонки), нужен
    для надёжного дедупа на клиенте: page-1 collectionItems видит лишь первую
    страницу, а этот сет — всё. Возвращаем и discogs_id (для discogs-релизов),
    и record_id (для user-records без discogs_id и для перехода с UUID-карточек).
    """
    result = await db.execute(
        select(Record.discogs_id, Record.id)
        .join(CollectionItem, CollectionItem.record_id == Record.id)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == current_user.id)
    )
    rows = result.all()
    discogs_ids = sorted({r[0] for r in rows if r[0]})
    record_ids = sorted({str(r[1]) for r in rows})
    return {"discogs_ids": discogs_ids, "record_ids": record_ids}


@router.get("/", response_model=list[CollectionResponse])
async def get_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение списка коллекций пользователя"""
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .order_by(Collection.sort_order, Collection.created_at)
    )
    collections = result.scalars().all()

    # Подсчёт элементов в каждой коллекции
    response = []
    for collection in collections:
        count_result = await db.execute(
            select(func.count(CollectionItem.id))
            .where(CollectionItem.collection_id == collection.id)
        )
        items_count = count_result.scalar()

        response.append(CollectionResponse(
            id=collection.id,
            user_id=collection.user_id,
            name=collection.name,
            description=collection.description,
            sort_order=collection.sort_order,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
            items_count=items_count or 0
        ))

    return response


@router.post("/", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создание новой коллекции"""
    # Получаем максимальный sort_order
    result = await db.execute(
        select(func.max(Collection.sort_order))
        .where(Collection.user_id == current_user.id)
    )
    max_order = result.scalar() or 0

    collection = Collection(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        sort_order=max_order + 1
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)

    return CollectionResponse(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        description=collection.description,
        sort_order=collection.sort_order,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        items_count=0
    )


@router.get("/{collection_id}", response_model=CollectionWithItems)
async def get_collection(
    collection_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("added_at", regex="^(added_at|price_desc|price_asc)$"),
    exclude_foldered: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получение коллекции с элементами"""
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    # record_id, вынесенные пользователем в папки (коллекции с бóльшим
    # sort_order). При exclude_foldered такие пластинки убираем из выдачи —
    # та же логика, что в /stats, чтобы оценка стоимости и список совпадали.
    base_filter = [CollectionItem.collection_id == collection_id]
    if exclude_foldered:
        foldered_result = await db.execute(
            select(CollectionItem.record_id)
            .join(Collection, CollectionItem.collection_id == Collection.id)
            .where(
                Collection.user_id == current_user.id,
                Collection.sort_order > collection.sort_order,
            )
        )
        foldered_record_ids = list(foldered_result.scalars().all())
        if foldered_record_ids:
            base_filter.append(CollectionItem.record_id.notin_(foldered_record_ids))

    # Определяем порядок сортировки
    if sort_by == "price_desc":
        order_clause = CollectionItem.estimated_price_rub.desc().nullslast()
    elif sort_by == "price_asc":
        order_clause = CollectionItem.estimated_price_rub.asc().nullslast()
    else:
        order_clause = CollectionItem.added_at.desc()

    # Получаем элементы с пагинацией.
    # Вторичная сортировка по id обязательна: при импорте создаётся пачка
    # CollectionItem с одинаковым added_at, и без стабильного тай-брейкера
    # OFFSET-пагинация возвращает строки в произвольном порядке — одна и та же
    # строка может попасть на две страницы, что ломает уникальность ключей в UI.
    offset = (page - 1) * per_page
    items_result = await db.execute(
        select(CollectionItem)
        .where(*base_filter)
        .options(
            selectinload(CollectionItem.record),
            selectinload(CollectionItem.user_photos),
        )
        .order_by(order_clause, CollectionItem.id)
        .offset(offset)
        .limit(per_page)
    )
    items = items_result.scalars().all()

    # Подсчёт общего количества
    count_result = await db.execute(
        select(func.count(CollectionItem.id))
        .where(*base_filter)
    )
    items_count = count_result.scalar() or 0

    return CollectionWithItems(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        description=collection.description,
        sort_order=collection.sort_order,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        items_count=items_count,
        items=[CollectionItemResponse(
            id=item.id,
            collection_id=item.collection_id,
            record_id=item.record_id,
            condition=item.condition,
            sleeve_condition=item.sleeve_condition,
            notes=item.notes,
            shelf_position=item.shelf_position,
            estimated_price_rub=float(item.estimated_price_rub) if item.estimated_price_rub else None,
            added_at=item.added_at,
            record=_item_record_brief(item)
        ) for item in items]
    )


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление коллекции"""
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    if data.name is not None:
        collection.name = data.name
    if data.description is not None:
        collection.description = data.description

    await db.commit()
    await db.refresh(collection)

    # Подсчёт элементов
    count_result = await db.execute(
        select(func.count(CollectionItem.id))
        .where(CollectionItem.collection_id == collection_id)
    )
    items_count = count_result.scalar() or 0

    return CollectionResponse(
        id=collection.id,
        user_id=collection.user_id,
        name=collection.name,
        description=collection.description,
        sort_order=collection.sort_order,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        items_count=items_count
    )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удаление коллекции"""
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    await db.delete(collection)
    await db.commit()


@router.post("/{collection_id}/items", response_model=CollectionItemResponse, status_code=status.HTTP_201_CREATED)
async def add_record_to_collection(
    collection_id: UUID,
    data: CollectionItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Добавление пластинки в коллекцию"""
    from app.api.records import get_or_create_record_by_discogs_id

    # Проверяем коллекцию
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    # Получаем Record: либо по discogs_id, либо по record_id
    if data.discogs_id:
        record = await get_or_create_record_by_discogs_id(data.discogs_id, db)
    elif data.record_id:
        result = await db.execute(select(Record).where(Record.id == data.record_id))
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пластинка не найдена"
            )
        # Папки не допускают дубликатов — возвращаем существующий item идемпотентно
        existing_result = await db.execute(
            select(CollectionItem)
            .where(
                CollectionItem.collection_id == collection_id,
                CollectionItem.record_id == record.id,
            )
            .options(selectinload(CollectionItem.record))
        )
        existing_item = existing_result.scalar_one_or_none()
        if existing_item:
            return CollectionItemResponse(
                id=existing_item.id,
                collection_id=existing_item.collection_id,
                record_id=existing_item.record_id,
                condition=existing_item.condition,
                sleeve_condition=existing_item.sleeve_condition,
                notes=existing_item.notes,
                shelf_position=existing_item.shelf_position,
                estimated_price_rub=float(existing_item.estimated_price_rub) if existing_item.estimated_price_rub else None,
                added_at=existing_item.added_at,
                record=existing_item.record,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Необходимо указать либо discogs_id, либо record_id"
        )

    # Whitelist: в коллекцию пускаем 'discogs', 'user' и 'store'. Все три при
    # будущем merge в Discogs переезжают через merged_into_id (soft-delete —
    # строка остаётся), а safe_merge_store_native_into ремапит collection_items
    # source→target. Физического DELETE записей в коде нет → CASCADE FK не
    # срабатывает, items не теряются.
    if record.source not in ("discogs", "user", "store"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пока эту пластинку нельзя добавить в коллекцию — её ещё нет на Discogs",
        )

    # Есть ли под эту пластинку активная бронь подарка в вишлисте?
    # Ищем не только точное совпадение записи: дарят часто другой прессинг
    # того же альбома (см. app/services/gift_match.py).
    from app.models.wishlist import Wishlist, WishlistItem
    from app.services.gift_match import find_gift_match

    gift_match = await find_gift_match(db, user_id=current_user.id, record=record)

    # Пункт вишлиста с активной бронью НЕ удаляем: сначала спросим у
    # пользователя, подарок ли это. Раньше удаление шло безусловно — бронь
    # теряла wishlist_item_id, навсегда зависала в BOOKED, даритель не получал
    # ни подтверждения, ни ачивки, а через 60 дней ему уходило письмо
    # «срок брони истёк» за уже вручённый подарок.
    if gift_match is None:
        wishlist_item_query = await db.execute(
            select(WishlistItem)
            .join(Wishlist)
            .where(
                Wishlist.user_id == current_user.id,
                WishlistItem.record_id == record.id
            )
        )
        wishlist_item = wishlist_item_query.scalar_one_or_none()

        # Если в вишлисте и брони нет — автоматически удаляем (атомарный перенос)
        if wishlist_item:
            await db.delete(wishlist_item)

    # Пересчитываем цену в рубли (lowest_price из Discogs)
    estimated_price_rub = None
    if record.estimated_price_min:
        settings = get_settings()
        usd_rub = await get_usd_rub_rate()
        params = PricingParams.from_settings(settings)
        estimated_price_rub = _record_rub(record, usd_rub, params)

    # Добавляем в коллекцию (дубликаты разрешены - можно иметь несколько копий одной пластинки)
    item = CollectionItem(
        collection_id=collection_id,
        record_id=record.id,
        condition=data.condition,
        sleeve_condition=data.sleeve_condition,
        notes=data.notes,
        estimated_price_rub=estimated_price_rub
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Запускаем фоновое скачивание обложки (если ещё не скачана)
    if record.discogs_id:
        await ensure_cover_cached(record.discogs_id, record.cover_image_url, db)

    # Эмиссия события ачивок (после коммита, не роняет основной запрос при ошибке)
    from app.services.achievements import emit_event
    from app.services.achievements.events import COLLECTION_ITEM_ADDED
    await emit_event(
        db,
        current_user.id,
        COLLECTION_ITEM_ADDED,
        {"collection_item_id": item.id, "record_id": record.id, "record": record},
    )

    # Milestone notifications: 100/500/1000-я пластинка в коллекции пользователя
    try:
        from sqlalchemy import func as _func
        from app.models.collection import Collection as _Collection, CollectionItem as _CI
        total = await db.scalar(
            select(_func.count(_CI.id)).join(_Collection).where(_Collection.user_id == current_user.id)
        )
        total = int(total or 0)
        if total in (100, 500, 1000):
            from app.services.notification_service import create_notification
            from app.services import push_copy
            milestone_title, milestone_body = push_copy.milestone_collection(total=total)
            await create_notification(
                db,
                user_id=current_user.id,
                type="milestone_unlocked",
                entity_type="milestone",
                entity_id=f"collection_{total}",
                data={
                    "milestone": f"collection_{total}",
                    "count": total,
                    "title": milestone_title,
                    "cover_url": getattr(record, "cover_image_url", None),
                },
                push_title=milestone_title,
                push_body=milestone_body,
            )
            await db.commit()
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).exception("Failed to emit milestone notification")

    return CollectionItemResponse(
        id=item.id,
        collection_id=item.collection_id,
        record_id=item.record_id,
        condition=item.condition,
        sleeve_condition=item.sleeve_condition,
        notes=item.notes,
        shelf_position=item.shelf_position,
        estimated_price_rub=float(item.estimated_price_rub) if item.estimated_price_rub else None,
        added_at=item.added_at,
        record=record,
        gift_match=GiftMatchInfo(
            booking_id=gift_match.booking.id,
            wishlist_item_id=gift_match.wishlist_item.id,
            match_kind=gift_match.match_kind,
            wished_record=RecordBrief.model_validate(gift_match.wishlist_item.record),
        ) if gift_match else None,
    )


@router.delete("/{collection_id}/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_record_from_collection(
    collection_id: UUID,
    record_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удаление пластинки из коллекции"""
    # Проверяем коллекцию
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    # Находим и удаляем элемент (first() т.к. могут быть дубликаты)
    result = await db.execute(
        select(CollectionItem)
        .where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.record_id == record_id
        )
    )
    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пластинка не найдена в коллекции"
        )

    removed_record_id = item.record_id
    await db.delete(item)
    await db.commit()

    # Пасхалка «Сомнения» считает циклы добавил-удалил по релизу. Строки уже
    # не будет, поэтому record_id передаём явно. Ошибки эмита глушатся внутри —
    # ачивки не должны валить удаление.
    from app.services.achievements.events import COLLECTION_ITEM_REMOVED
    from app.services.achievements.evaluator import emit_event

    await emit_event(
        db, current_user.id, COLLECTION_ITEM_REMOVED, {"record_id": str(removed_record_id)}
    )


@router.delete("/{collection_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_collection(
    collection_id: UUID,
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удаление конкретного элемента (копии) из коллекции по item_id"""
    # Проверяем коллекцию
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    # Находим и удаляем конкретный элемент по item_id
    result = await db.execute(
        select(CollectionItem)
        .where(
            CollectionItem.id == item_id,
            CollectionItem.collection_id == collection_id
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Элемент не найден в коллекции"
        )

    removed_record_id = item.record_id
    await db.delete(item)
    await db.commit()

    # Пасхалка «Сомнения» считает циклы добавил-удалил по релизу. Строки уже
    # не будет, поэтому record_id передаём явно. Ошибки эмита глушатся внутри —
    # ачивки не должны валить удаление.
    from app.services.achievements.events import COLLECTION_ITEM_REMOVED
    from app.services.achievements.evaluator import emit_event

    await emit_event(
        db, current_user.id, COLLECTION_ITEM_REMOVED, {"record_id": str(removed_record_id)}
    )


@router.get("/{collection_id}/stats", response_model=CollectionStats)
async def get_collection_stats(
    collection_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Статистика коллекции"""
    # Проверяем доступ
    result = await db.execute(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.user_id == current_user.id
        )
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    # Все владения пользователя по ВСЕМ коллекциям (вариант A, как total_records
    # ниже). Папка — это группировка, а не вынос с полки: релиз, разложенный по
    # жанровой папке, всё ещё в коллекции и обязан считаться в стоимости и в
    # «оценено». Раньше breakdown бежал по текущей коллекции с вычетом foldered —
    # числитель («оценено X») и знаменатель («из Y») мерились по разным
    # множествам, из-за чего раскладывание релизов по папкам занижало и счётчик,
    # и сумму. Теперь оба по одному множеству — все уникальные владения.
    result = await db.execute(
        select(CollectionItem)
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == current_user.id)
        .options(selectinload(CollectionItem.record))
    )
    items = result.scalars().all()

    # Дедуп по record_id: одна пластинка может лежать в главной коллекции и в
    # папке одновременно — считаем её один раз. При коллизии предпочитаем копию
    # с посчитанным estimated_price_rub, чтобы не потерять стоимость на дубле.
    by_record: dict = {}
    for item in items:
        existing = by_record.get(item.record_id)
        if existing is None:
            by_record[item.record_id] = item
        elif existing.estimated_price_rub is None and item.estimated_price_rub is not None:
            by_record[item.record_id] = item
    unique_items = list(by_record.values())

    # «В коллекции» (вариант A): все уникальные владения пользователя по ВСЕМ
    # коллекциям — папки это группировка, а не вынос с полки, поэтому из счёта
    # не вычитаются. Breakdown ниже (стоимость/годы/жанры) остаётся по текущей
    # коллекции через unique_items.
    total_records = await db.scalar(
        select(func.count(func.distinct(CollectionItem.record_id)))
        .join(Collection, CollectionItem.collection_id == Collection.id)
        .where(Collection.user_id == current_user.id)
    ) or 0
    total_min = 0.0
    total_max = 0.0
    total_median = 0.0
    total_rub = 0.0
    records_with_price = 0
    records_by_year = {}
    records_by_genre = {}
    years = []

    most_expensive_item = None
    most_expensive_rub = 0.0

    for item in unique_items:
        record = item.record

        if record.estimated_price_min:
            total_min += float(record.estimated_price_min)
        if record.estimated_price_max:
            total_max += float(record.estimated_price_max)
        if record.estimated_price_median:
            total_median += float(record.estimated_price_median)

        # «Оценено» = есть хоть какая-то цена. Discogs у редких релизов отдаёт
        # median=NULL → цена живёт только в min; считать priced строго по min
        # рассинхронило бы счётчик со стоимостью (та берёт median or min).
        if record.estimated_price_median or record.estimated_price_min:
            records_with_price += 1

        if item.estimated_price_rub:
            rub = float(item.estimated_price_rub)
            total_rub += rub
            if rub > most_expensive_rub:
                most_expensive_rub = rub
                most_expensive_item = item

        if record.year:
            years.append(record.year)
            records_by_year[record.year] = records_by_year.get(record.year, 0) + 1

        if record.genre:
            records_by_genre[record.genre] = records_by_genre.get(record.genre, 0) + 1

    settings = get_settings()
    usd_rub = await get_usd_rub_rate()

    # Эффективный множитель — агрегированно по коллекции (rub / (usd × rate))
    aggregate_markup = (
        round(total_rub / (total_min * usd_rub), 2)
        if total_min > 0 and usd_rub > 0
        else 1.0
    )

    return CollectionStats(
        total_records=total_records,
        total_estimated_value_min=total_min if total_min > 0 else None,
        total_estimated_value_max=total_max if total_max > 0 else None,
        total_estimated_value_median=total_median if total_median > 0 else None,
        total_estimated_value_rub=round(total_rub, 2) if total_rub > 0 else None,
        usd_rub_rate=usd_rub,
        ru_markup=aggregate_markup,
        most_expensive=most_expensive_item.record if most_expensive_item else None,
        most_expensive_price_rub=most_expensive_rub if most_expensive_item else None,
        records_with_price=records_with_price,
        records_by_year=records_by_year,
        records_by_genre=records_by_genre,
        oldest_record_year=min(years) if years else None,
        newest_record_year=max(years) if years else None
    )


def _record_from_basic_information(basic: dict) -> Record:
    """Строит slim Record из basic_information коллекции Discogs — без detail
    API-вызова. Полный payload (tracklist, цены) дозагружается лениво при первом
    открытии детали (_ensure_record_discogs_payload)."""
    artists = basic.get("artists") or []
    artist = ", ".join(a.get("name", "").strip() for a in artists if a.get("name")) or "Unknown"

    labels = basic.get("labels") or []
    label = labels[0].get("name") if labels else None
    catalog = labels[0].get("catno") if labels else None

    formats = basic.get("formats") or []
    format_type = formats[0].get("name") if formats else None
    format_description = ", ".join(formats[0].get("descriptions", []) or []) if formats else None

    year = basic.get("year") or None
    if year == 0:
        year = None

    return Record(
        discogs_id=str(basic.get("id")),
        discogs_master_id=str(basic["master_id"]) if basic.get("master_id") else None,
        title=basic.get("title", "Unknown"),
        artist=artist,
        label=label,
        catalog_number=catalog,
        year=year,
        genre=", ".join(basic.get("genres", []) or []) or None,
        style=", ".join(basic.get("styles", []) or []) or None,
        format_type=format_type,
        format_description=format_description,
        cover_image_url=basic.get("cover_image"),
        thumb_image_url=basic.get("thumb"),
    )


@router.post("/import/discogs")
async def import_discogs_collection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One-time импорт коллекции из Discogs в основную коллекцию юзера.

    Требует подключённого Discogs (свой OAuth-токен). Идёт под токеном юзера —
    его лимит 60/min. Дедуп по discogs_id: уже добавленные пропускаются."""
    from app.services.discogs import DiscogsService
    from app.services.discogs_oauth import user_creds

    creds = user_creds(current_user)
    if not creds or not current_user.discogs_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала подключите Discogs в настройках",
        )

    # Основная коллекция юзера (первая по порядку).
    result = await db.execute(
        select(Collection)
        .where(Collection.user_id == current_user.id)
        .order_by(Collection.sort_order, Collection.created_at)
    )
    collection = result.scalars().first()
    if not collection:
        collection = Collection(user_id=current_user.id, name="Моя коллекция")
        db.add(collection)
        await db.flush()

    discogs = DiscogsService()
    try:
        releases = await discogs.get_collection_releases(
            current_user.discogs_username, creds
        )
    except Exception:
        logger.exception("Discogs collection fetch failed for %s", current_user.discogs_username)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось получить коллекцию из Discogs. Попробуйте позже.",
        )

    # Какие record_id уже в этой коллекции — чтобы не плодить дубли.
    existing_result = await db.execute(
        select(CollectionItem.record_id).where(
            CollectionItem.collection_id == collection.id
        )
    )
    existing_record_ids = set(existing_result.scalars().all())

    # Курс и параметры считаем один раз — чтобы проставить рублёвую стоимость
    # тем записям, у которых уже есть цена (estimated_price_min). Свежие slim-
    # записи без цены получат её из фоновой задачи update_prices_batch (4:00)
    # или через ручной /recalculate-prices.
    settings = get_settings()
    usd_rub = await get_usd_rub_rate()
    params = PricingParams.from_settings(settings)

    imported = 0
    skipped = 0
    for basic in releases:
        discogs_id = str(basic.get("id"))
        if not discogs_id or discogs_id == "None":
            continue

        rec_result = await db.execute(
            select(Record).where(Record.discogs_id == discogs_id)
        )
        record = rec_result.scalar_one_or_none()
        if record is None:
            record = _record_from_basic_information(basic)
            db.add(record)
            try:
                await db.flush()
            except IntegrityError:
                # Параллельная вставка того же discogs_id — читаем существующую.
                await db.rollback()
                rec_result = await db.execute(
                    select(Record).where(Record.discogs_id == discogs_id)
                )
                record = rec_result.scalar_one_or_none()
                if record is None:
                    continue

        if record.id in existing_record_ids:
            skipped += 1
            continue

        price_rub = (
            _record_rub(record, usd_rub, params)
            if record.estimated_price_min
            else None
        )
        db.add(CollectionItem(
            collection_id=collection.id,
            record_id=record.id,
            estimated_price_rub=price_rub,
        ))
        existing_record_ids.add(record.id)
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "total": len(releases)}


