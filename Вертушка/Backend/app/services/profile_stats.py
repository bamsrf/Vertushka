"""
Fun stats публичного профиля — «ротирующие фишки» коллекции.

Один источник правды на два потребителя:
  * HTML-страница профиля (`web/routes.py`) — рисует их каруселью;
  * OG-картинка (`services/og_image.py`) — печатает первые N строк.

Поэтому факт возвращается не готовой разметкой, а списком кусков
`{"text": str, "bold": bool}`: HTML оборачивает жирные куски в <b>,
картинка красит их акцентным цветом. Экранирование остаётся на стороне
потребителя — тексты содержат пользовательские строки (artist/genre).
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.record import Record

logger = logging.getLogger(__name__)


_GENRE_RU = {
    # {rel} → склоняется на «релиз / релиза / релизов» по числу.
    # Жанры без дефиса (электроника, классика, джаз) идут как прилагательное в род. падеже.
    "rock": "рок-{rel}",
    "pop": "поп-{rel}",
    "electronic": "электронных {rel}",
    "hip hop": "хип-хоп {rel}",
    "hip-hop": "хип-хоп {rel}",
    "jazz": "джазовых {rel}",
    "classical": "классических {rel}",
    "funk / soul": "фанк- и соул-{rel}",
    "funk": "фанк-{rel}",
    "soul": "соул-{rel}",
    "reggae": "регги-{rel}",
    "blues": "блюзовых {rel}",
    "folk, world, & country": "фолк- и кантри-{rel}",
    "folk": "фолк-{rel}",
    "country": "кантри-{rel}",
    "latin": "латинских {rel}",
    "stage & screen": "саундтрек-{rel}",
    "non-music": "non-music {rel}",
    "children's": "детских {rel}",
    "brass & military": "бравурных {rel}",
}


def ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Русское склонение существительного по числу.
    one — для 1, 21, 31… (last digit 1, кроме 11–14)
    few — для 2–4, 22–24… (last digit 2–4, кроме 12–14)
    many — для 0, 5–20, 25–30…
    """
    n_abs = abs(int(n))
    if 11 <= n_abs % 100 <= 14:
        return many
    last = n_abs % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def genre_label(genre: str, count: int) -> str:
    """Возвращает русскую форму жанра + склонённое 'релиз/-а/-ов' по числу."""
    rel = ru_plural(count, "релиз", "релиза", "релизов")
    key = (genre or "").strip().lower()
    template = _GENRE_RU.get(key) or f"{genre}-{{rel}}"
    return template.replace("{rel}", rel)


def _stat(icon: str, *parts: tuple[str, bool]) -> dict:
    """Собирает факт из чередующихся кусков (текст, жирный?)."""
    return {
        "icon": icon,
        "parts": [{"text": text, "bold": bold} for text, bold in parts if text],
    }


def stat_plain(stat: dict) -> str:
    """Плоский текст факта — для alt/description и отладки."""
    return "".join(p["text"] for p in stat["parts"])


# Порядок фактов на OG-картинке отличается от страницы: в ленте фишки
# крутятся все по очереди, а в превью помещаются три — значит нужны самые
# «цепляющие». Список — приоритет по иконке; всё, чего тут нет, идёт следом
# в исходном порядке.
_OG_PRIORITY = ["💸", "👑", "🕰️", "💎", "📅", "🌍", "🎨", "📻", "🎧", "🏷️", "⚡"]


def pick_for_og(stats: list[dict], limit: int = 3) -> list[dict]:
    """Отбирает самые интересные факты для превью-картинки."""
    def rank(stat: dict) -> int:
        icon = stat.get("icon", "")
        return _OG_PRIORITY.index(icon) if icon in _OG_PRIORITY else len(_OG_PRIORITY)

    return sorted(stats, key=rank)[:limit]


async def compute_fun_stats(user_id: UUID, db: AsyncSession) -> list[dict]:
    """
    Считает список фактов о коллекции пользователя.

    Все агрегации идут поверх DISTINCT record_id, чтобы один и тот же релиз
    из разных папок не задваивал статистику. Правило показа: значение > 0
    и проходит порог — иначе факт не попадает в список.

    Порядок в списке — приоритет: первые элементы уходят в OG-картинку.
    Любая ошибка гасится в пустой список: фишки — украшение, из-за них
    профиль падать не должен.
    """
    stats: list[dict] = []
    try:
        # Подзапрос с уникальными record_id юзера
        user_records_subq = (
            select(CollectionItem.record_id.distinct().label("rid"))
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.user_id == user_id)
            .subquery()
        )
        ur_join = user_records_subq.join(Record, Record.id == user_records_subq.c.rid)

        # Цветные пластинки. Реальный цвет у Discogs лежит в formats[0].text →
        # discogs_data->>'vinyl_color_raw', а НЕ в format_description (там
        # «LP, Album, Limited Edition…»). Считаем цветной, если:
        #   * в vinyl_color_raw есть слово любого цвета, КРОМЕ чёрного
        #     («Red w/ Black Smoke» — цветная, «Cosmic Black» — нет); или
        #   * в vinyl_color_raw либо format_description есть неспецифичный
        #     маркер (coloured/translucent/marbled/…) — старая логика.
        # Намеренно не через color_family(): у неё black первым в приоритете,
        # и «Red w/ Black Smoke» ушла бы в чёрные. \y — граница слова в
        # Postgres ARE (аналог \b), иначе red ловится внутри hundred.
        color_raw = func.coalesce(Record.discogs_data.op("->>")("vinyl_color_raw"), "")
        fmt_desc = func.coalesce(Record.format_description, "")
        nonblack_color_re = (
            r"\y(white|teal|turquoise|red|blue|green|yellow|orange|purple|"
            r"pink|gold|silver|clear)\y"
        )
        colored_marker_re = r"colou?r|translucent|marbled|splatter|picture disc|glow"
        color_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(or_(
                color_raw.op("~*")(nonblack_color_re),
                color_raw.op("~*")(colored_marker_re),
                fmt_desc.op("~*")(colored_marker_re),
            ))
        ) or 0

        # Топ-жанр (Discogs хранит несколько через запятую — расщепляем в Python)
        genre_rows = await db.execute(
            select(Record.genre)
            .select_from(ur_join)
            .where(Record.genre.isnot(None), Record.genre != "")
        )
        genre_counter: dict[str, int] = {}
        for (genre_str,) in genre_rows:
            for g in (genre_str or "").split(","):
                g_clean = g.strip()
                if g_clean:
                    genre_counter[g_clean] = genre_counter.get(g_clean, 0) + 1
        top_genre, top_genre_count = (None, 0)
        if genre_counter:
            top_genre, top_genre_count = max(genre_counter.items(), key=lambda kv: kv[1])

        # Декада с наибольшим количеством
        year_rows = await db.execute(
            select(Record.year)
            .select_from(ur_join)
            .where(Record.year.isnot(None), Record.year > 1900)
        )
        decade_counter: dict[int, int] = {}
        for (yr,) in year_rows:
            if yr is None:
                continue
            d = (int(yr) // 10) * 10
            decade_counter[d] = decade_counter.get(d, 0) + 1
        top_decade, top_decade_count = (None, 0)
        if decade_counter:
            top_decade, top_decade_count = max(decade_counter.items(), key=lambda kv: kv[1])

        # Стран и лейблов (distinct по уникальным записям)
        countries_count = await db.scalar(
            select(func.count(func.distinct(Record.country)))
            .select_from(ur_join)
            .where(Record.country.isnot(None), Record.country != "")
        ) or 0

        labels_count = await db.scalar(
            select(func.count(func.distinct(Record.label)))
            .select_from(ur_join)
            .where(Record.label.isnot(None), Record.label != "")
        ) or 0

        # Самая старая пластинка
        oldest_row = await db.execute(
            select(Record.year, Record.artist, Record.title)
            .select_from(ur_join)
            .where(Record.year.isnot(None), Record.year > 1900)
            .order_by(Record.year.asc())
            .limit(1)
        )
        oldest = oldest_row.first()

        # Самая свежая пластинка
        newest_row = await db.execute(
            select(Record.year)
            .select_from(ur_join)
            .where(Record.year.isnot(None), Record.year > 1900)
            .order_by(Record.year.desc())
            .limit(1)
        )
        newest = newest_row.first()

        # Релизы текущего года.
        # added_at в БД хранится без таймзоны — работаем с naive UTC,
        # чтобы asyncpg не падал на сравнении offset-aware с naive.
        now_utc_naive = datetime.utcnow()
        current_year = now_utc_naive.year
        fresh_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(Record.year == current_year)
        ) or 0

        # Distinct artists
        artists_count = await db.scalar(
            select(func.count(func.distinct(Record.artist)))
            .select_from(ur_join)
            .where(Record.artist.isnot(None), Record.artist != "")
        ) or 0

        # Топ-артист (count distinct records по artist)
        top_artist_row = await db.execute(
            select(Record.artist, func.count(Record.id).label("cnt"))
            .select_from(ur_join)
            .where(Record.artist.isnot(None), Record.artist != "")
            .group_by(Record.artist)
            .order_by(func.count(Record.id).desc())
            .limit(1)
        )
        top_artist = top_artist_row.first()

        # Первые прессы / Каноничные / Коллекционка
        rare_count = await db.scalar(
            select(func.count(Record.id))
            .select_from(ur_join)
            .where(or_(Record.is_first_press == True, Record.is_canon == True, Record.is_collectible == True))
        ) or 0

        # Самая дорогая (по estimated_price_rub в коллекции юзера).
        # select_from(CollectionItem) — иначе SQLA вывел бы FROM из Record и
        # JOIN-цепочка не сошлась бы.
        priciest_row = await db.execute(
            select(Record.artist, Record.title, CollectionItem.estimated_price_rub)
            .select_from(CollectionItem)
            .join(Collection, CollectionItem.collection_id == Collection.id)
            .join(Record, CollectionItem.record_id == Record.id)
            .where(
                Collection.user_id == user_id,
                CollectionItem.estimated_price_rub.isnot(None),
                CollectionItem.estimated_price_rub > 0,
            )
            .order_by(CollectionItem.estimated_price_rub.desc())
            .limit(1)
        )
        priciest = priciest_row.first()

        # Возраст коллекции (дни от первой добавленной записи)
        first_added = await db.scalar(
            select(func.min(CollectionItem.added_at))
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(Collection.user_id == user_id)
        )

        # Новых за последние 7 дней
        week_ago = now_utc_naive - timedelta(days=7)
        new_this_week = await db.scalar(
            # DISTINCT: копия в папке не делает пластинку «новой» дважды.
            select(func.count(func.distinct(CollectionItem.record_id)))
            .join(Collection, Collection.id == CollectionItem.collection_id)
            .where(
                Collection.user_id == user_id,
                CollectionItem.added_at >= week_ago,
            )
        ) or 0

        # === Сборка списка ===
        # Все формы существительных/прилагательных склоняются по числу через ru_plural.
        if color_count > 0:
            phrase = ru_plural(color_count, "цветная пластинка", "цветные пластинки", "цветных пластинок")
            stats.append(_stat("🎨", (str(color_count), True), (f" {phrase}", False)))
        if top_genre and top_genre_count >= 2:
            label = genre_label(top_genre, top_genre_count)
            stats.append(_stat("🎧", (str(top_genre_count), True), (f" {label}", False)))
        if top_decade and top_decade_count >= 2:
            word = ru_plural(top_decade_count, "пластинка", "пластинки", "пластинок")
            stats.append(_stat(
                "📻",
                (str(top_decade_count), True), (f" {word} из ", False), (f"{top_decade}-х", False),
            ))
        if fresh_count > 0:
            word = ru_plural(fresh_count, "релиз", "релиза", "релизов")
            stats.append(_stat("🚀", (str(fresh_count), True), (f" {word} {current_year}-го", False)))
        if countries_count >= 2:
            word = ru_plural(countries_count, "страна", "страны", "стран")
            stats.append(_stat("🌍", (str(countries_count), True), (f" {word} в коллекции", False)))
        if labels_count >= 3:
            phrase = ru_plural(labels_count, "разный лейбл", "разных лейбла", "разных лейблов")
            stats.append(_stat("🏷️", (str(labels_count), True), (f" {phrase}", False)))
        if artists_count >= 5:
            phrase = ru_plural(artists_count, "разный артист", "разных артиста", "разных артистов")
            stats.append(_stat("🎙️", (str(artists_count), True), (f" {phrase}", False)))
        if top_artist and top_artist[1] >= 2:
            artist_name = (top_artist[0] or "").strip()
            if len(artist_name) > 22:
                artist_name = artist_name[:22] + "…"
            stats.append(_stat("👑", ("Топ-артист: ", False), (artist_name, True)))
        if oldest and oldest[0]:
            artist_name = (oldest[1] or "").strip()
            if len(artist_name) > 18:
                artist_name = artist_name[:18] + "…"
            suffix = f" · {artist_name}" if artist_name else ""
            stats.append(_stat("🕰️", ("Самая старая: ", False), (str(oldest[0]), True), (suffix, False)))
        if newest and newest[0] and (not oldest or newest[0] != oldest[0]):
            stats.append(_stat("🆕", ("Самая свежая: ", False), (str(newest[0]), True)))
        if rare_count > 0:
            phrase = ru_plural(rare_count, "редкое издание", "редких издания", "редких изданий")
            stats.append(_stat("💎", (str(rare_count), True), (f" {phrase}", False)))
        if priciest and priciest[2] and priciest[2] >= 1000:
            price_fmt = f"{int(priciest[2]):,}".replace(",", " ")
            stats.append(_stat("💸", ("Самая дорогая: ", False), (f"{price_fmt} ₽", True)))
        if first_added:
            fa = first_added.replace(tzinfo=None) if first_added.tzinfo else first_added
            days = (now_utc_naive - fa).days
            if days >= 365:
                years = days // 365
                word = ru_plural(years, "год", "года", "лет")
                stats.append(_stat("📅", ("Собирает ", False), (str(years), True), (f" {word}", False)))
            elif days >= 90:
                months = max(1, days // 30)
                word = ru_plural(months, "месяц", "месяца", "месяцев")
                stats.append(_stat("📅", ("Собирает ", False), (str(months), True), (f" {word}", False)))
        if new_this_week >= 2:
            phrase = ru_plural(new_this_week, "новая пластинка", "новые пластинки", "новых пластинок")
            stats.append(_stat("⚡", (str(new_this_week), True), (f" {phrase} за неделю", False)))
    except Exception as e:
        logger.warning("fun_stats computation failed: %s", e)
        return []

    return stats
