"""Имена доменных событий, на которые реагирует система ачивок."""

# Коллекции
COLLECTION_ITEM_ADDED = "collection_item_added"

# Вишлист
WISHLIST_ITEM_ADDED = "wishlist_item_added"

# Подарки
GIFT_BOOKED = "gift_booked"
GIFT_COMPLETED = "gift_completed"    # подарок дошёл (status=COMPLETED) — для J2/J3/J4/J6
GIFT_RECEIVED = "gift_received"      # юзер получил подарок (recipient_user_id) — для J5

# Профиль и юзер
AVATAR_SET = "avatar_set"
PROFILE_SHARED_ENABLED = "profile_shared_enabled"
PROFILE_VIEW = "profile_view"  # инкремент view_count чужим юзером

# Социальное
FOLLOW_CREATED = "follow_created"      # юзер подписался на кого-то
FOLLOW_RECEIVED = "follow_received"    # на юзера кто-то подписался

# Сообщения (K-серия, трек 3)
MESSAGE_SENT = "message_sent"          # юзер отправил сообщение в чат

# Вклад / спрос / первопроходец (K-серия, треки 2/4/5)
USER_RECORD_CREATED = "user_record_created"  # юзер добавил ручной релиз (source='user')
RECORD_WANTED = "record_wanted"              # пластинку из коллекции юзера кто-то добавил в вишлист

# Рефералы (Phase 2 / INV-серия)
REFERRED_USER_REGISTERED = "referred_user_registered"   # кто-то зарегался по реф-ссылке текущего юзера
REFERRED_USER_ACTIVATED = "referred_user_activated"     # приведённый дошёл до состояния «активен» (≥10 пластинок, ≥30 дней)

# Маркет (M-серия)
OFFER_CLICKED = "offer_clicked"            # affiliate-переход в магазин
PRICE_DRAWER_OPENED = "price_drawer_opened"  # открыл карточку цен

# Периодика
DAILY_TICK = "daily_tick"
