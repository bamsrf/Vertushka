"""
API для экспорта данных пользователя в CSV
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.collection import Collection, CollectionItem
from app.models.wishlist import Wishlist, WishlistItem
from app.api.auth import get_current_user

router = APIRouter()

COLLECTION_COLUMNS = [
    "Folder", "Artist", "Title", "Label", "CatalogNumber",
    "Format", "Year", "Genre", "Notes", "DiscogsID", "DateAdded",
]

WISHLIST_COLUMNS = [
    "Artist", "Title", "Label", "CatalogNumber",
    "Format", "Year", "Genre", "Priority", "Notes", "DiscogsID", "DateAdded",
]


def _format_date(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


async def _build_collection_csv(
    db: AsyncSession, user_id
) -> str:
    """Собрать CSV коллекции."""
    collections_result = await db.execute(
        select(Collection)
        .where(Collection.user_id == user_id)
        .order_by(Collection.sort_order)
    )
    collections = collections_result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(COLLECTION_COLUMNS)

    for collection in collections:
        items_result = await db.execute(
            select(CollectionItem)
            .where(CollectionItem.collection_id == collection.id)
            .options(selectinload(CollectionItem.record))
            .order_by(CollectionItem.added_at.desc())
        )
        items = items_result.scalars().all()

        for item in items:
            r = item.record
            writer.writerow([
                collection.name,
                r.artist if r else "",
                r.title if r else "",
                r.label or "",
                r.catalog_number or "",
                r.format_type or "",
                r.year or "",
                r.genre or "",
                item.notes or "",
                r.discogs_id or "",
                _format_date(item.added_at),
            ])

    return output.getvalue()


async def _build_wishlist_csv(
    db: AsyncSession, user_id
) -> str:
    """Собрать CSV вишлиста."""
    result = await db.execute(
        select(Wishlist)
        .where(Wishlist.user_id == user_id)
        .options(
            selectinload(Wishlist.items).selectinload(WishlistItem.record)
        )
    )
    wishlist = result.scalar_one_or_none()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(WISHLIST_COLUMNS)

    if wishlist and wishlist.items:
        for item in sorted(wishlist.items, key=lambda i: i.added_at or datetime.min, reverse=True):
            r = item.record
            writer.writerow([
                r.artist if r else "",
                r.title if r else "",
                r.label or "",
                r.catalog_number or "",
                r.format_type or "",
                r.year or "",
                r.genre or "",
                item.priority if item.priority is not None else "",
                item.notes or "",
                r.discogs_id or "",
                _format_date(item.added_at),
            ])

    return output.getvalue()


@router.get("/collection.csv")
async def export_collection_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Экспорт коллекции в CSV"""
    csv_data = await _build_collection_csv(db, current_user.id)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="vertushka_collection_{datetime.utcnow().strftime("%Y%m%d")}.csv"'
        },
    )


@router.get("/wishlist.csv")
async def export_wishlist_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Экспорт вишлиста в CSV"""
    csv_data = await _build_wishlist_csv(db, current_user.id)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="vertushka_wishlist_{datetime.utcnow().strftime("%Y%m%d")}.csv"'
        },
    )
