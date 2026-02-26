"""
API для работы с коллекциями
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.record import Record
from app.models.collection import Collection, CollectionItem
from app.api.auth import get_current_user
from app.config import get_settings
from app.services.exchange import get_usd_rub_rate
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionItemCreate,
    CollectionItemUpdate,
    CollectionItemResponse,
    CollectionWithItems,
    CollectionStats,
)

router = APIRouter()


@router.post("/recalculate-prices")
async def recalculate_prices(
    db: AsyncSession = Depends(get_db)
):
    """Пересчёт цен: перезапрашивает lowest_price из Discogs (в USD) и пересчитывает рубли."""
    from app.services.discogs import DiscogsService

    # Все элементы всех коллекций с записями
    items_result = await db.execute(
        select(CollectionItem)
        .options(selectinload(CollectionItem.record))
    )
    items = items_result.scalars().all()

    if not items:
        return {"updated": 0, "total": 0}

    settings = get_settings()
    usd_rub = await get_usd_rub_rate()
    discogs = DiscogsService()

    # Группируем по discogs_id чтобы не запрашивать одну пластинку дважды
    records_map: dict[str, Record] = {}
    for item in items:
        if item.record and item.record.discogs_id:
            records_map[item.record.discogs_id] = item.record

    # Перезапрашиваем цены из Discogs (теперь с curr_abbr=USD)
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
    updated_items = 0
    for item in items:
        record = item.record
        if record and record.estimated_price_min:
            item.estimated_price_rub = round(
                float(record.estimated_price_min) * usd_rub * settings.ru_vinyl_markup, 2
            )
            updated_items += 1
        else:
            item.estimated_price_rub = None

    await db.commit()

    return {
        "updated_records": updated_records,
        "updated_items": updated_items,
        "total_items": len(items),
        "usd_rub_rate": usd_rub,
        "markup": settings.ru_vinyl_markup,
    }


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

    # Определяем порядок сортировки
    if sort_by == "price_desc":
        order_clause = CollectionItem.estimated_price_rub.desc().nullslast()
    elif sort_by == "price_asc":
        order_clause = CollectionItem.estimated_price_rub.asc().nullslast()
    else:
        order_clause = CollectionItem.added_at.desc()

    # Получаем элементы с пагинацией
    offset = (page - 1) * per_page
    items_result = await db.execute(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
        .options(selectinload(CollectionItem.record))
        .order_by(order_clause)
        .offset(offset)
        .limit(per_page)
    )
    items = items_result.scalars().all()

    # Подсчёт общего количества
    count_result = await db.execute(
        select(func.count(CollectionItem.id))
        .where(CollectionItem.collection_id == collection_id)
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
            record=item.record
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

    # Проверяем, есть ли эта пластинка в вишлисте текущего пользователя
    from app.models.wishlist import Wishlist, WishlistItem

    wishlist_item_query = await db.execute(
        select(WishlistItem)
        .join(Wishlist)
        .where(
            Wishlist.user_id == current_user.id,
            WishlistItem.record_id == record.id
        )
    )
    wishlist_item = wishlist_item_query.scalar_one_or_none()

    # Если в вишлисте - автоматически удаляем (атомарный перенос)
    if wishlist_item:
        await db.delete(wishlist_item)

    # Пересчитываем цену в рубли (lowest_price из Discogs)
    estimated_price_rub = None
    if record.estimated_price_min:
        settings = get_settings()
        usd_rub = await get_usd_rub_rate()
        estimated_price_rub = round(
            float(record.estimated_price_min) * usd_rub * settings.ru_vinyl_markup, 2
        )

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
        record=record
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

    await db.delete(item)
    await db.commit()


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

    await db.delete(item)
    await db.commit()


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
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Коллекция не найдена"
        )

    # Получаем все пластинки коллекции
    result = await db.execute(
        select(CollectionItem)
        .where(CollectionItem.collection_id == collection_id)
        .options(selectinload(CollectionItem.record))
    )
    items = result.scalars().all()

    total_records = len(items)
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

    for item in items:
        record = item.record

        if record.estimated_price_min:
            total_min += float(record.estimated_price_min)
            records_with_price += 1
        if record.estimated_price_max:
            total_max += float(record.estimated_price_max)
        if record.estimated_price_median:
            total_median += float(record.estimated_price_median)

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

    return CollectionStats(
        total_records=total_records,
        total_estimated_value_min=total_min if total_min > 0 else None,
        total_estimated_value_max=total_max if total_max > 0 else None,
        total_estimated_value_median=total_median if total_median > 0 else None,
        total_estimated_value_rub=round(total_rub, 2) if total_rub > 0 else None,
        usd_rub_rate=usd_rub,
        ru_markup=settings.ru_vinyl_markup,
        most_expensive=most_expensive_item.record if most_expensive_item else None,
        most_expensive_price_rub=most_expensive_rub if most_expensive_item else None,
        records_with_price=records_with_price,
        records_by_year=records_by_year,
        records_by_genre=records_by_genre,
        oldest_record_year=min(years) if years else None,
        newest_record_year=max(years) if years else None
    )


