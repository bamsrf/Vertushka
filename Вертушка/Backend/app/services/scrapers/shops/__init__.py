"""
Per-shop парсеры.

Чтобы добавить магазин:
1. Создать `<slug>.py` с классом-наследником `BaseStoreParser` и декоратором
   `@register_parser("<slug>")`.
2. Добавить `from app.services.scrapers.shops import <slug>  # noqa` ниже.
3. В БД (или через Store-сидинг) создать запись `Store(slug="<slug>", parser_class="<slug>", ...)`.

Парсер автоматически попадёт в реестр и будет доступен через `get_parser("<slug>")`.

# --- Регистрация парсеров ---
"""

from app.services.scrapers.shops import korobkavinyla  # noqa: F401
from app.services.scrapers.shops import plastinka_com  # noqa: F401
from app.services.scrapers.shops import vinyl_ru  # noqa: F401
from app.services.scrapers.shops import stoprobotvinyl  # noqa: F401
from app.services.scrapers.shops import found  # noqa: F401
from app.services.scrapers.shops import doctorhead  # noqa: F401
