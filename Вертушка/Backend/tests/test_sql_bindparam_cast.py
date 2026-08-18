"""Guard на `:param::type` в SQL — форма, которая ломается молча.

Инцидент, который сторожит файл. В метрике покрытия обложек стоял запрос

    WHERE last_seen_at >= :d::date AND last_seen_at < :d::date + 1

SQLAlchemy не распознаёт `:d` как bindparam, когда следом идёт `::`, и отдаёт
драйверу текст с двоеточиями как есть. asyncpg падает с `syntax error at or
near ":"`. Исключение уходило в APScheduler, метрика не считалась ни разу с
16 августа 2026 — и об этом никто не знал, потому что джоба падала тихо.

Правильная форма — `CAST(:d AS date)`.

Тест смотрит ТОЛЬКО строковые литералы (через tokenize), поэтому упоминания
битой формы в комментариях и докстрингах — как в этом файле — не ложные
срабатывания.
"""
import io
import re
import tokenize
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# :имя:: — параметр, за которым сразу каст. Именно эта склейка и не работает.
_BAD = re.compile(r":\w+::")


def _string_literals(path: Path) -> list[tuple[int, str]]:
    """(номер строки, содержимое) для всех строковых литералов файла."""
    src = path.read_text(encoding="utf-8")
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.STRING:
                out.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Битый файл — забота других тестов, не этого.
        return []
    return out


def test_no_bindparam_followed_by_cast_in_sql():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        for line_no, literal in _string_literals(path):
            if _BAD.search(literal):
                rel = path.relative_to(APP.parent)
                offenders.append(f"{rel}:{line_no}: {literal.strip()[:120]}")

    assert not offenders, (
        "SQL с `:param::type` — SQLAlchemy не увидит параметр, asyncpg упадёт на "
        "syntax error. Используйте CAST(:param AS type):\n  " + "\n  ".join(offenders)
    )


def test_guard_actually_catches_the_broken_form():
    """Проверка самого детектора: без неё тест выше мог бы «проходить» впустую."""
    assert _BAD.search("WHERE d >= :d::date")
    assert _BAD.search("SELECT :x::int")
    # Что ловить НЕ должен: голый каст без параметра и обычные URL со схемой.
    assert not _BAD.search("SELECT discogs_id::text FROM t")
    assert not _BAD.search("https://coverartarchive.org/release/x/front")
    assert not _BAD.search("CAST(:d AS date)")


def test_date_cast_params_are_not_strings():
    """`CAST(:d AS date)` требует объект date, а не строку.

    Второй заход на те же грабли. Сначала было `:d::date` — SQLAlchemy не видел
    параметр, asyncpg падал на синтаксисе. Замена на `CAST(:d AS date)` починила
    синтаксис, но принесла новую поломку: asyncpg выводит тип аргумента из каста
    и на строке '2026-08-18' падает с `'str' object has no attribute 'toordinal'`.

    Метрика при этом не падала — блок обёрнут в try/except — просто `cold_per_dau`
    молча не считался. Ровно то число, ради которого инструментацию и ставили.
    """
    import inspect
    from app.tasks import cover_coverage_tasks as t

    src = inspect.getsource(t.report_cover_coverage)
    assert "CAST(:d AS date)" in src
    assert "date.fromisoformat(day[\"date\"])" in src, (
        "в CAST(:d AS date) обязан идти объект date, иначе asyncpg падает"
    )
