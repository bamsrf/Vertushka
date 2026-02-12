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
]

