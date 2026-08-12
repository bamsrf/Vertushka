"""Нечёткий поиск по дампу: сузили перебор, но не правило принятия.

Замеры на проде 12.08 (13.1 млн строк). По умолчанию pg_trgm отдаёт кандидатов
от 0.3, и на широком артисте это миллионы строк: «Various Artists» + «The Sound
Of Jazz» = 995k × 830k, запрос идёт 60.9 c и не укладывается в statement_timeout
(30 c). Тогда он отменяется, листинг проваливается на платный шаг, и Discogs
находит релиз, лежащий в нашем же дампе: все 5 663 «находки» API оказались
уже у нас (100%).

Порог 0.4 — не подобранное число, а доказуемая граница: принимаем score >= 1.4
из двух similarity, каждая максимум 1.0, значит по каждому полю нужно минимум
0.4. Кандидат ниже 0.4 не мог быть принят никогда.

Проверено также эмпирически на 14 527 принятых нечётких матчах: ниже 0.4 по
любому полю — 14 штук (0.096%), и все это листинги, чей текст перезаписался
более поздним обходом уже ПОСЛЕ матча.
"""
import inspect
import re

from app.services import listing_matcher


def _sql() -> str:
    return inspect.getsource(listing_matcher._lookup_in_dump_index)


def _code_only() -> str:
    """Исходник без комментариев — иначе проверки цепляются за пояснения в тексте."""
    lines = []
    for line in _sql().splitlines():
        if line.strip().startswith("#"):
            continue
        lines.append(line.split("  # ")[0])
    return "\n".join(lines)


def test_threshold_is_applied_before_the_query():
    """Без него pg_trgm берёт дефолтные 0.3 и запрос уходит в таймаут."""
    code = _code_only()
    assert "SET LOCAL pg_trgm.similarity_threshold" in code


def test_threshold_is_transaction_scoped():
    """SET LOCAL, а не set_limit(): порог не должен протекать через пул соединений.

    set_limit() живёт в сессии, а сессия переиспользуется пулом — соседний
    запрос получил бы чужой порог.
    """
    code = _code_only()
    assert "set_limit(" not in code


def test_threshold_matches_the_acceptance_bound():
    """0.4 выведено из правила принятия, а не подобрано.

    score >= 1.4 из двух similarity по 1.0 максимум → каждое поле >= 0.4.
    Ниже — впустую расширяем перебор, выше — теряем принимаемые совпадения.
    """
    assert listing_matcher._DUMP_TRGM_THRESHOLD == 0.4


def test_scoring_and_acceptance_unchanged():
    """Порог перебора — не порог качества. Оценка и граница принятия прежние."""
    sql = _sql()
    assert "(similarity(artist, :a) + similarity(title, :t)) AS score" in sql
    assert "row[\"score\"] < 1.4" in sql


def test_threshold_is_not_interpolated_from_user_input():
    """В f-строку уходит только наша константа-число, не данные листинга."""
    sql = _sql()
    m = re.search(r'SET LOCAL pg_trgm\.similarity_threshold = \{(\w+)\}', sql)
    assert m, "порог должен подставляться из именованной константы"
    assert m.group(1) == "_DUMP_TRGM_THRESHOLD"
    assert isinstance(listing_matcher._DUMP_TRGM_THRESHOLD, float)


def test_filter_stays_on_indexed_columns():
    """Фильтр обязан идти по полям с GIN-индексами (ix_dri_artist/title_trgm).

    Проверка от рецидива: попытка 12.08 заменить два `%` на склейку
    `artist || ' ' || title` оказалась в 2 раза МЕДЛЕННЕЕ на обычных запросах
    (Pink Floyd 1.89 c → 3.64 c) — длинная строка даёт больше триграмм, и GIN
    обходит их дольше. Индекс склейки удалён, вариант закрыт.
    """
    sql = _sql()
    assert "WHERE artist % :a AND title % :t" in sql
    assert "(artist || ' ' || title)" not in sql


def test_exact_paths_untouched():
    """Штрихкод и каталожный номер — точные, к ним нечёткая правка не относится."""
    sql = _sql()
    assert "WHERE barcode_norm = ANY(:bs)" in sql
    assert "WHERE catalog_norm = :c" in sql
