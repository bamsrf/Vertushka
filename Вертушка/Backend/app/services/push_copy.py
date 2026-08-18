"""
Копирайт push-уведомлений. Единственное место, где живут тексты пушей.

Правила тона (см. docs/plans/PLAN_NOTIFICATIONS_V3.md § «Тон пушей»):
- Обращение на «ты» везде.
- Констатация, не восклицание: точка вместо «!», без «Ура»/«Поздравляем».
- Без императивов-CTA («Открой ленту», «Поделись») — на push и так нажимают.
- Цифра конкретная, она и есть эмоция: «−34%», «3 200 ₽».
- Ноль гендера: настоящее время или конструкция без глагола.
- Эмодзи не используем.
- Title — субъект новости (пластинка, человек), body — что случилось + цифра.

Каждая функция возвращает `(title, body)` и принимает примитивы, а не ORM-объекты,
чтобы тексты можно было проверять без БД.
"""
from __future__ import annotations

NBSP = " "
MINUS = "−"  # настоящий минус, не дефис — иначе «-34%» выглядит как перенос


def plural_records(n: int) -> str:
    """«1 пластинка», «3 пластинки», «11 пластинок»."""
    mod10, mod100 = n % 10, n % 100
    if 11 <= mod100 <= 14:
        return "пластинок"
    if mod10 == 1:
        return "пластинка"
    if 2 <= mod10 <= 4:
        return "пластинки"
    return "пластинок"


def money(value: float | int | None) -> str | None:
    """3200.0 → «3 200 ₽» (неразрывные пробелы, чтобы не рвалось на локскрине)."""
    if value is None:
        return None
    return f"{int(value):,}".replace(",", NBSP) + f"{NBSP}₽"


def record_line(artist: str | None, title: str | None) -> str:
    """«Miles Davis — Kind of Blue». Без артиста — только название."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    if artist and title:
        return f"{artist} — {title}"
    return title or artist or "Пластинка"


def _join(*parts: str | None) -> str:
    """Склейка непустых кусков body через « · »."""
    return " · ".join(p for p in parts if p)


# --- Радар и вишлист -------------------------------------------------------


def wishlist_in_stock(
    *,
    artist: str | None,
    title: str | None,
    min_price: float | None,
    store_name: str | None,
) -> tuple[str, str]:
    """Пластинка с радара появилась в наличии.

    Намеренно не «снова в продаже»: джоб ловит переход в in_stock, который для
    юзера может быть первым появлением вообще.
    """
    price = money(min_price)
    return (
        record_line(artist, title),
        _join("Есть в наличии", f"от {price}" if price else None, store_name),
    )


def wishlist_in_stock_alt(
    *,
    artist: str | None,
    title: str | None,
    min_price: float | None,
    store_name: str | None,
) -> tuple[str, str]:
    """В продаже другое издание того же мастера."""
    price = money(min_price)
    return (
        record_line(artist, title),
        _join("В продаже другое издание", f"от {price}" if price else None, store_name),
    )


def wishlist_price_drop(
    *,
    artist: str | None,
    title: str | None,
    old_price: float,
    new_price: float,
    drop_pct: int,
) -> tuple[str, str]:
    """Цена упала (но не до исторического минимума)."""
    body = _join(
        f"{MINUS}{drop_pct}%" if drop_pct else None,
        f"{money(old_price)} → {money(new_price)}",
    )
    return record_line(artist, title), body


def wishlist_all_time_low(
    *,
    title: str | None,
    new_price: float,
    previous_low: float | None,
) -> tuple[str, str]:
    """Новый исторический минимум цены.

    `previous_low` — минимум по истории ДО текущего снапшота. Если его нет,
    сравнивать не с чем и вторую половину body опускаем.
    """
    return (
        f"Минимальная цена: {(title or '').strip()}".strip().rstrip(":"),
        _join(
            money(new_price),
            f"прошлый минимум {money(previous_low)}" if previous_low is not None else None,
        ),
    )


def plural_editions(n: int) -> str:
    """«1 другое издание», «3 других издания», «11 других изданий»."""
    mod10, mod100 = n % 10, n % 100
    if 11 <= mod100 <= 14:
        return "других изданий"
    if mod10 == 1:
        return "другое издание"
    if 2 <= mod10 <= 4:
        return "других издания"
    return "других изданий"


def weekly_digest(
    *, count: int, artists: list[str], alt_count: int = 0
) -> tuple[str, str]:
    """Недельная сводка по вишлисту. В body — имена, ради которых открывают.

    `alt_count` — аналоги (другое издание того же мастера). Считаются отдельно
    от точных совпадений: смешать их в одну цифру значит обещать «твою
    пластинку» там, где в наличии чужой прессинг.
    """
    names = ", ".join(artists[:3])

    # Только аналоги: субъект новости — они, врать про «из вишлиста» нельзя.
    if count == 0 and alt_count > 0:
        return (
            f"За неделю: {alt_count} {plural_editions(alt_count)}",
            names or "Другие издания пластинок из вишлиста",
        )

    title = f"За неделю: {count} {plural_records(count)} из вишлиста"
    if alt_count > 0:
        tail = f"и ещё {alt_count} {plural_editions(alt_count)}"
        body = f"{tail} · {names}" if names else tail
    else:
        body = names
    return title, body or "Подробности в ленте радара"


# --- Социальные ------------------------------------------------------------


def _profile_body(username: str | None, collection_count: int | None) -> str:
    handle = f"@{username}" if username else None
    size = (
        f"{collection_count} {plural_records(collection_count)} в коллекции"
        if collection_count
        else None
    )
    return _join(handle, size) or "Новый профиль"


def follow_request(
    *, name: str, username: str | None, collection_count: int | None = None
) -> tuple[str, str]:
    """Заявка на подписку (приватный профиль)."""
    return f"{name} хочет подписаться", _profile_body(username, collection_count)


def new_follower(
    *, name: str, username: str | None, collection_count: int | None = None
) -> tuple[str, str]:
    """Новый подписчик (публичный профиль — подписка без заявки)."""
    return f"{name} — твой новый подписчик", _profile_body(username, collection_count)


def follow_approved(*, name: str) -> tuple[str, str]:
    """Твою заявку на подписку одобрили.

    Имя держим в именительном: display_name склонять нечем («Коллекция Ксения
    теперь доступна» — брак, а падеж произвольного никнейма не вычислить).
    """
    return "Заявка принята", f"{name} открывает тебе коллекцию"


# --- Подарки ---------------------------------------------------------------


def gift_booked_anonymous(*, artist: str | None, title: str | None) -> tuple[str, str]:
    """Подарок забронирован, имя дарителя скрыто (дефолт)."""
    return (
        "Кто-то забронировал подарок",
        f"«{record_line(artist, title)}» из твоего вишлиста",
    )


def gift_booked_revealed(
    *, gifter_name: str, artist: str | None, title: str | None
) -> tuple[str, str]:
    """Подарок забронирован, владелец включил reveal_gifter_to_owner.

    Не «Подарок от {name}»: предлог требует родительного падежа («от Влада»),
    а склонять произвольный display_name нечем.
    """
    return f"{gifter_name} дарит тебе пластинку", f"«{record_line(artist, title)}»"


def gift_confirmed(*, owner_name: str, title: str | None) -> tuple[str, str]:
    """Дарителю: получатель добавил подарок в коллекцию.

    Имя — подлежащее в именительном, по той же причине, что и выше.
    """
    return (
        "Подарок на месте",
        f"{owner_name} добавляет «{(title or '').strip()}» в коллекцию",
    )


# --- Прогресс --------------------------------------------------------------


def achievement_unlocked(*, title_ru: str, flavor_ru: str = "") -> tuple[str, str]:
    """Ачивка. В body — готовый flavor_ru из определения: там уже нужный голос."""
    return f"Ачивка: {title_ru}", (flavor_ru or "").strip() or "Открыта новая ачивка"


def level_up(*, label: str, flavor_ru: str = "") -> tuple[str, str]:
    """Новый уровень архетипа. В body — флейвор ступени: голос уже нужный."""
    return (
        f"Новый уровень: {label}",
        (flavor_ru or "").strip() or "Ты поднялся на ступень выше",
    )


def milestone_collection(*, total: int) -> tuple[str, str]:
    """Веха коллекции: 100 / 500 / 1000 пластинок."""
    return f"В коллекции {total} {plural_records(total)}", "Полка заметно тяжелее"
