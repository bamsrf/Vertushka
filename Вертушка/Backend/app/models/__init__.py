"""
Модели базы данных Вертушка
"""
from app.models.user import User
from app.models.record import Record
from app.models.collection import Collection, CollectionItem
from app.models.wishlist import Wishlist, WishlistItem
from app.models.gift_booking import GiftBooking
from app.models.follow import Follow
from app.models.profile_share import ProfileShare
from app.models.search_cache import SearchCache
from app.models.user_photo import UserRecordPhoto
from app.models.collection_value_snapshot import CollectionValueSnapshot
from app.models.waitlist import WaitlistEntry

__all__ = [
    "User",
    "Record",
    "Collection",
    "CollectionItem",
    "Wishlist",
    "WishlistItem",
    "GiftBooking",
    "Follow",
    "ProfileShare",
    "SearchCache",
    "UserRecordPhoto",
    "CollectionValueSnapshot",
    "WaitlistEntry",
]

