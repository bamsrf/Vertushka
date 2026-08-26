"""Тесты парсера «Дом Винила» (vinylhouse.ru).

Фикстуры — компактные слепки живой разметки CS-Cart (осмотр 26.08.2026):
карточка листинга, пагинатор, блок подкатегорий, страница товара с грейдами.
"""
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup

from app.services.scrapers.shops.vinylhouse import (
    _category_paths,
    _clean_price,
    _extract_cards,
    _full_image,
    _max_page,
    _parse_card,
    _parse_title,
)


def _card_html(
    *,
    pid: str = "29959",
    href: str = "https://vinylhouse.ru/klassicheskiy-rok/10cc-1978-2-great-pop-classics-vinilovaya-plastinka/",
    title: str = "10CC – 1978 – 2 Great Pop Classics — Виниловая пластинка",
    price: str = "4&nbsp;990.00",
    img: str = "https://vinylhouse.ru/images/thumbnails/150/150/detailed/77/10cc.jpg",
) -> str:
    return f"""
    <div class="ty-grid-list__item ty-quick-view-button__wrapper">
      <form action="https://vinylhouse.ru/" method="post" name="product_form_{pid}">
        <input type="hidden" name="product_data[{pid}][product_id]" value="{pid}" />
        <div class="ty-grid-list__image">
          <a href="{href}">
            <img class="ty-pict cm-image" id="det_img_{pid}" src="{img}" />
          </a>
        </div>
        <div class="ty-grid-list__item-name">
          <a href="{href}" class="product-title" title="{title}">{title}</a>
        </div>
        <span class="ty-price-num" id="sec_discounted_price_{pid}">{price}</span>
      </form>
    </div>
    """


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---- Тайтл --------------------------------------------------------------- #

def test_title_artist_year_album():
    artist, year, album, tail = _parse_title(
        "AC/DC – 1976 – Dirty Deeds Done Dirt Cheap — Виниловая пластинка"
    )
    assert artist == "AC/DC"
    assert year == 1976
    assert album == "Dirty Deeds Done Dirt Cheap"
    assert tail == "Виниловая пластинка"


def test_title_with_edition_suffix():
    # Хвост издания уходит в альбом, а не теряется
    artist, year, album, _ = _parse_title(
        "AC/DC – 1979 – Highway To Hell – Atlantic — Виниловая пластинка"
    )
    assert artist == "AC/DC"
    assert year == 1979
    assert album == "Highway To Hell – Atlantic"


def test_title_artist_with_digits_and_no_album():
    # «1989 Australian Rocks – 1989» — цифры в имени артиста не принимаются
    # за год (год — только ОТДЕЛЬНОЕ поле), а альбома может не быть вовсе
    artist, year, album, _ = _parse_title(
        "1989 Australian Rocks – 1989 — Виниловая пластинка"
    )
    assert artist == "1989 Australian Rocks"
    assert year == 1989
    assert album is None


def test_title_hyphenated_artist_survives():
    # Дефис без пробелов — не разделитель полей
    artist, year, album, _ = _parse_title(
        "Jay-Z – 2003 – The Black Album — Виниловая пластинка"
    )
    assert artist == "Jay-Z"
    assert year == 2003
    assert album == "The Black Album"


def test_title_without_year():
    artist, year, album, _ = _parse_title(
        "Pink Floyd – The Dark Side Of The Moon — Виниловая пластинка"
    )
    assert artist == "Pink Floyd"
    assert year is None
    assert album == "The Dark Side Of The Moon"


# ---- Карточка ------------------------------------------------------------ #

def test_card_parses_all_fields():
    dto = _parse_card(_extract_cards(_soup(_card_html()))[0])
    assert dto is not None
    assert dto.external_id == "29959"
    assert dto.artist_raw == "10CC"
    assert dto.year_raw == 1978
    assert dto.price_rub == Decimal("4990.00")
    assert dto.status == "in_stock"
    # Превью 150×150 развёрнуто в полноразмер
    assert dto.image_url == "https://vinylhouse.ru/images/detailed/77/10cc.jpg"
    assert dto.raw_payload["album"] == "2 Great Pop Classics"


def test_card_external_id_is_product_id_not_url():
    # Один товар в двух категориях = два URL, но один product_id
    a = _parse_card(_extract_cards(_soup(_card_html(
        href="https://vinylhouse.ru/klassicheskiy-rok/x-vinilovaya-plastinka/"
    )))[0])
    b = _parse_card(_extract_cards(_soup(_card_html(
        href="https://vinylhouse.ru/progressive/x-vinilovaya-plastinka/"
    )))[0])
    assert a.external_id == b.external_id == "29959"


def test_card_without_product_id_is_dropped():
    html = _card_html().replace('name="product_data[29959][product_id]"', 'name="other"')
    html = html.replace("product_form_29959", "product_form")
    assert _parse_card(_extract_cards(_soup(html))[0]) is None


def test_card_without_price_is_on_request():
    dto = _parse_card(_extract_cards(_soup(_card_html(price="")))[0])
    assert dto is not None
    assert dto.price_rub is None
    assert dto.status == "on_request"


def test_card_merch_tail_is_dropped():
    dto = _parse_card(_extract_cards(_soup(_card_html(
        title="The Beatles – Кружка коллекционера — Сувенир"
    )))[0])
    assert dto is None


def test_card_media_tails_accepted():
    for tail in ("Виниловая пластинка", '7" сингл', "Винил LP"):
        dto = _parse_card(_extract_cards(_soup(_card_html(
            title=f"Artist – 1980 – Album — {tail}"
        )))[0])
        assert dto is not None, tail


def test_price_with_nbsp_and_spaces():
    assert _clean_price("4\xa0990.00") == Decimal("4990.00")
    assert _clean_price("12 500.00") == Decimal("12500.00")
    assert _clean_price("") is None
    assert _clean_price("0.00") is None


def test_full_image_strips_any_thumbnail_size():
    assert _full_image(
        "https://vinylhouse.ru/images/thumbnails/60/86/detailed/21/x.jpg"
    ) == "https://vinylhouse.ru/images/detailed/21/x.jpg"
    assert _full_image(None) is None


# ---- Пагинация и категории ----------------------------------------------- #

def test_max_page_from_pagination():
    html = '''<a href="https://vinylhouse.ru/klassicheskiy-rok/page-2/">2</a>
              <a href="https://vinylhouse.ru/klassicheskiy-rok/page-9/">9</a>'''
    assert _max_page(html) == 9
    assert _max_page("<html>без пагинатора</html>") == 1


def test_category_paths_from_menu():
    html = '''
      <a class="ty-menu__item-link" href="https://vinylhouse.ru/beatles/">Beatles</a>
      <a class="ty-menu__item-link" href="https://vinylhouse.ru/jazz/">Jazz</a>
      <a class="ty-menu__item-link" href="https://vinylhouse.ru/memorabilia/">Сувениры</a>
      <a class="ty-menu__item-link" href="https://vinylhouse.ru/dom-vinyla/">Дом</a>
      <a class="ty-menu__item-link" href="https://vinylhouse.ru/jazz/">Jazz повтор</a>
    '''
    paths = _category_paths(_soup(html).find_all("a", class_="ty-menu__item-link"))
    # Мерч и пустая витрина бренда исключены, дубли схлопнуты
    assert paths == ["/beatles/", "/jazz/"]


def test_subcategory_paths():
    # Живая разметка CS-Cart: <ul class="subcategories"><li class="ty-subcategories__item">
    html = '''
      <ul class="subcategories clearfix">
        <li class="ty-subcategories__item">
          <a href="https://vinylhouse.ru/beatles/dzhon-lennon/"><img /></a>
        </li>
        <li class="ty-subcategories__item">
          <a href="https://vinylhouse.ru/beatles/pol-makkartni/"><img /></a>
        </li>
      </ul>
    '''
    subs = _category_paths(_soup(html).select("ul.subcategories a[href]"))
    assert subs == ["/beatles/dzhon-lennon/", "/beatles/pol-makkartni/"]


# ---- Сквозной обход на стабах -------------------------------------------- #

class _StubHttp:
    """Отдаёт заранее заданные страницы; чужие URL — пустая категория."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.requested: list[str] = []

    async def get_text(self, url: str, **kw) -> str:
        self.requested.append(url)
        return self.pages.get(url, "<html></html>")


@pytest.mark.asyncio
async def test_crawl_walks_subcategories_and_dedupes():
    from app.services.scrapers.shops.vinylhouse import VinylhouseParser

    menu = '<a class="ty-menu__item-link" href="https://vinylhouse.ru/beatles/">B</a>'
    beatles = f'''
      <ul class="subcategories clearfix">
        <li class="ty-subcategories__item">
          <a href="https://vinylhouse.ru/beatles/dzhon-lennon/"><img /></a>
        </li>
      </ul>
      {_card_html(pid="100", title="The Beatles – 1969 – Abbey Road — Виниловая пластинка")}
    '''
    # В подкатегории тот же товар (pid=100) и один новый
    lennon = (
        _card_html(pid="100", title="The Beatles – 1969 – Abbey Road — Виниловая пластинка")
        + _card_html(pid="200", title="John Lennon – 1971 – Imagine — Виниловая пластинка")
    )
    http = _StubHttp({
        "https://vinylhouse.ru/": menu,
        "https://vinylhouse.ru/beatles/": beatles,
        "https://vinylhouse.ru/beatles/dzhon-lennon/": lennon,
    })
    parser = VinylhouseParser(http=http)

    dtos = [d async for d in parser.crawl_full()]
    ids = [d.external_id for d in dtos]
    assert ids == ["100", "200"]  # дубль между категориями схлопнут
    # Страницы за пагинатором не запрашивались (page-2 нигде нет)
    assert not any("page-" in u for u in http.requested)


@pytest.mark.asyncio
async def test_crawl_follows_pagination_to_last_page():
    from app.services.scrapers.shops.vinylhouse import VinylhouseParser

    menu = '<a class="ty-menu__item-link" href="https://vinylhouse.ru/jazz/">J</a>'
    page1 = (
        _card_html(pid="1", title="A – 1970 – One — Виниловая пластинка")
        + '<a href="https://vinylhouse.ru/jazz/page-2/">2</a>'
    )
    page2 = _card_html(pid="2", title="B – 1971 – Two — Виниловая пластинка")
    http = _StubHttp({
        "https://vinylhouse.ru/": menu,
        "https://vinylhouse.ru/jazz/": page1,
        "https://vinylhouse.ru/jazz/page-2/": page2,
    })
    parser = VinylhouseParser(http=http)

    ids = [d.external_id async for d in parser.crawl_full()]
    assert ids == ["1", "2"]
    assert "https://vinylhouse.ru/jazz/page-2/" in http.requested
    assert "https://vinylhouse.ru/jazz/page-3/" not in http.requested


# ---- Страница товара ------------------------------------------------------ #

_PRODUCT_PAGE = """
<html><body>
  <h1>10CC – 1978 – 2 Great Pop Classics — Виниловая пластинка</h1>
  <form name="product_form_29959">
    <input type="hidden" name="product_data[29959][product_id]" value="29959" />
  </form>
  <span class="ty-price-num" id="discounted_price_29959">4&nbsp;990.00</span>
  <span class="ty-qty-in-stock ty-control-group__item" id="in_stock_info_29959">В наличии</span>
  <img class="ty-pict" src="https://vinylhouse.ru/images/thumbnails/500/500/detailed/77/x.jpg" />
  <div id="content_description">
    Коллекционное голландское переиздание. Состояние: конверт Near Mint пластинки&nbsp;Near Mint
  </div>
  <script>var strings = {text_out_of_stock: 'Нет в наличии'};</script>
</body></html>
"""


class _OnePageHttp:
    def __init__(self, html: str):
        self.html = html

    async def get_text(self, url: str, **kw) -> str:
        return self.html


@pytest.mark.asyncio
async def test_parse_listing_condition_and_stock():
    from app.services.scrapers.shops.vinylhouse import VinylhouseParser

    parser = VinylhouseParser(http=_OnePageHttp(_PRODUCT_PAGE))
    dto = await parser.parse_listing(
        "https://vinylhouse.ru/klassicheskiy-rok/10cc-1978-2-great-pop-classics-vinilovaya-plastinka/"
    )
    assert dto.external_id == "29959"       # тот же id, что у карточки листинга
    assert dto.artist_raw == "10CC"
    assert dto.year_raw == 1978
    assert dto.price_rub == Decimal("4990.00")
    # «Нет в наличии» в JS-словаре темы не сбивает определение наличия
    assert dto.status == "in_stock"
    assert dto.condition == "пластинка Near Mint / конверт Near Mint"


@pytest.mark.asyncio
async def test_parse_listing_out_of_stock_without_marker():
    from app.services.scrapers.shops.vinylhouse import VinylhouseParser

    html = _PRODUCT_PAGE.replace(
        '<span class="ty-qty-in-stock ty-control-group__item" id="in_stock_info_29959">В наличии</span>',
        "",
    )
    parser = VinylhouseParser(http=_OnePageHttp(html))
    dto = await parser.parse_listing("https://vinylhouse.ru/x/y-vinilovaya-plastinka/")
    assert dto.status == "out_of_stock"
