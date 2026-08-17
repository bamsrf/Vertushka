"""Серии «Машина времени» (E*) и «Полная дискография» (H*).

Обе серии много месяцев стояли каркасом: `evaluator=_stub` возвращал
`unlocked=False` безусловно, то есть ачивки существовали в каталоге, но открыть
их было нельзя. Первый тест здесь — сторож именно от этого: заглушка,
вернувшаяся в коллекционную серию, снова сделает её недостижимой, и снаружи
это выглядит не как поломка, а как «просто пока не дотянул».

Остальное — арифметика окон, которую легко сломать на единицу.
"""
import pytest

from app.services.achievements.definitions.series import discography, eras
from app.services.achievements.registry import all_definitions

#: Серии про содержимое коллекции. INV_* (рефералы) сюда не входит — это
#: отдельная невыпущенная фича, а не забытый каркас.
COLLECTION_SERIES = {
    "eras",
    "discography",
    "scale",
    "rarity",
    "genres",
    "geography",
    "formats",
    "foundation",
}


class TestNoStubsLeft:
    def test_collection_series_have_real_evaluators(self):
        stubs = [
            d.code
            for d in all_definitions()
            if d.series in COLLECTION_SERIES and d.evaluator.__name__ == "_stub"
        ]
        assert stubs == [], (
            f"Заглушки в коллекционных сериях: {stubs}. Такая ачивка видна в "
            f"каталоге, но не открывается никогда."
        )


class TestErasWindows:
    @pytest.mark.parametrize(
        "years,expected",
        [
            ([], 0),
            ([1975], 1),
            (list(range(1970, 1980)), 10),          # ровно десятилетие
            (list(range(1969, 1979)), 10),          # скользящее, не календарное
            ([1970, 1971, 1975, 1976, 1977], 3),
            ([1970, 1970, 1971], 2),                # дубли не удлиняют цепочку
        ],
    )
    def test_longest_consecutive_run(self, years, expected):
        assert eras._longest_consecutive_run(sorted(years)) == expected

    def test_sliding_window_accepts_non_calendar_decade(self):
        """Ключевое продуктовое решение: 1969–1978 засчитывается.

        Календарная трактовка отбрасывала бы такую коллекцию, хотя это те же
        десять лет подряд.
        """
        assert eras._longest_consecutive_run(list(range(1969, 1979))) >= eras.DECADE_SPAN

    def test_covered_decades_are_calendar(self):
        """META, в отличие от E6, считает именно календарные десятилетия."""
        assert eras._covered_decades([1955, 1962, 1969, 2024], 2026) == {1950, 1960, 2020}

    def test_covered_decades_ignore_pre_1950_and_future(self):
        assert eras._covered_decades([1901, 1949, 2099], 2026) == set()


class TestErasDefinitions:
    def test_all_eras_recheck_on_daily_tick(self):
        """Год у импортированных записей проставляется обогащением из дампа.

        Без DAILY_TICK серия зависела бы от того, добавит ли юзер ещё одну
        пластинку после того, как год наконец появился.
        """
        from app.services.achievements.events import DAILY_TICK

        missing = [
            d.code for d in eras.DEFINITIONS if DAILY_TICK not in d.triggers
        ]
        assert missing == []


class TestDiscographyThresholds:
    def test_h2_requires_meaningful_discography(self):
        """«Полная дискография» артиста с одним альбомом — не достижение."""
        assert discography.H2_MIN_ALBUMS >= 3

    def test_h2_runs_only_on_daily_tick(self):
        """Перебор до 25 дискографий не должен висеть на добавлении пластинки."""
        from app.services.achievements.events import COLLECTION_ITEM_ADDED, DAILY_TICK

        h2 = next(d for d in discography.DEFINITIONS if d.code == discography.H2_CODE)
        assert h2.triggers == (DAILY_TICK,)
        assert COLLECTION_ITEM_ADDED not in h2.triggers

    def test_studio_album_classification_delegates_to_release_type(self):
        """H2 не должен заводить свои регексы: тип релиза считает один модуль.

        Дублирование правил между SQL и питоном в этом проекте уже разъезжалось
        (см. docstring services/release_type.py).
        """
        from app.services.release_type import ALBUM, classify_group

        assert discography.ALBUM is ALBUM
        assert discography.classify_group is classify_group

    @pytest.mark.parametrize(
        "fmts,is_studio",
        [
            (['Vinyl, LP, Album'], True),
            (['Vinyl, LP, Album, Compilation', 'CD, Compilation'], False),
            (['CD, Album, Sampler'], False),          # промо
            (['Vinyl, 12", 33 ⅓ RPM, EP'], False),
            (['Vinyl, 7"'], False),                   # сингл по носителю
            (['DVD-Video, Album'], False),            # концертник
        ],
    )
    def test_what_counts_as_studio_album(self, fmts, is_studio):
        from app.services.release_type import ALBUM, classify_group

        assert (classify_group(fmts) == ALBUM) is is_studio
