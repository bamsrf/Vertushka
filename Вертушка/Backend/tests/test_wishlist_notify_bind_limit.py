"""Guard на bind-limit asyncpg в задачах уведомлений.

Прод-инцидент (ревью 23.08.2026): после обхода краулера, бампающего
updated_at всему маркету, окно «recent» в emit_wishlist_in_stock_notifications
вбирало ~54k листингов, и запрос alt-версий разворачивал
`Record.discogs_master_id.in_(masters)` + `not_in(instock_record_ids)`
в 48 961 bind-параметр при лимите asyncpg 32 767. Задача падала после
каждого обхода — в 02:00 и 14:00, дважды в сутки.

Фикс — `_id_filter`: на PostgreSQL один array-бинд (`= ANY(:ids)` /
`!= ALL(:ids)`), на прочих диалектах прежний in_/not_in.
"""
import ast
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from app.models.record import Record
from app.models.wishlist import WishlistItem
from app.tasks.notification_tasks import _id_filter

# Жёсткий потолок протокола asyncpg: параметров в запросе не может быть больше.
ASYNCPG_BIND_LIMIT = 32_767

# Больше замеренного в инциденте (48 961) — фильтр обязан переварить.
INCIDENT_SCALE = 50_000

TASKS_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "tasks" / "notification_tasks.py"
)


def _compiled(stmt, dialect):
    # render_postcompile разворачивает expanding-параметры (in_) в реальные
    # бинды — ровно то, что уедет в драйвер. Без него in_ выглядит как один
    # параметр-список и лимит asyncpg в тесте не виден.
    return stmt.compile(dialect=dialect, compile_kwargs={"render_postcompile": True})


def test_plain_in_explodes_binds_documenting_the_incident():
    """Сам механизм падения: голый in_ по списку — параметр на элемент."""
    ids = [str(i) for i in range(ASYNCPG_BIND_LIMIT + 1)]
    stmt = select(Record.id).where(Record.discogs_master_id.in_(ids))
    compiled = _compiled(stmt, postgresql.dialect())
    assert len(compiled.params) > ASYNCPG_BIND_LIMIT


def test_pg_filter_is_single_array_bind():
    ids = [str(uuid.uuid4()) for _ in range(INCIDENT_SCALE)]
    stmt = select(Record.id).where(
        _id_filter(Record.discogs_master_id, ids, dialect="postgresql")
    )
    compiled = _compiled(stmt, postgresql.dialect())
    assert len(compiled.params) == 1, (
        f"ожидали один array-бинд, получили {len(compiled.params)} — "
        "снова упрёмся в лимит asyncpg 32 767"
    )
    assert "ANY (" in str(compiled)


def test_pg_negated_filter_is_single_array_bind():
    ids = [uuid.uuid4() for _ in range(INCIDENT_SCALE)]
    stmt = select(WishlistItem.id).where(
        _id_filter(WishlistItem.record_id, ids, dialect="postgresql", negate=True)
    )
    compiled = _compiled(stmt, postgresql.dialect())
    assert len(compiled.params) == 1
    assert "ALL (" in str(compiled)


def test_pg_filter_accepts_sets():
    """_emit_alt_versions передаёт set[UUID] — порядок не важен, форма та же."""
    ids = {uuid.uuid4() for _ in range(100)}
    stmt = select(WishlistItem.id).where(
        _id_filter(WishlistItem.record_id, ids, dialect="postgresql", negate=True)
    )
    assert len(_compiled(stmt, postgresql.dialect()).params) == 1


def test_non_pg_dialect_falls_back_to_in():
    """SQLite (тестовый диалект) не умеет = ANY(array) — там обычный IN."""
    ids = [str(uuid.uuid4()) for _ in range(5)]
    stmt = select(Record.id).where(
        _id_filter(Record.discogs_master_id, ids, dialect="sqlite")
    )
    sql = str(_compiled(stmt, sqlite.dialect()))
    assert "IN (" in sql and "ANY" not in sql

    neg = select(Record.id).where(
        _id_filter(Record.discogs_master_id, ids, dialect="sqlite", negate=True)
    )
    neg_sql = str(_compiled(neg, sqlite.dialect()))
    assert ("NOT IN" in neg_sql or "NOT (" in neg_sql) and "ALL" not in neg_sql


def test_no_unbounded_in_over_python_lists_in_tasks():
    """В notification_tasks.py не осталось in_/not_in по неограниченным спискам.

    Разрешены только литеральные списки фиксированного размера (статусы,
    типы) — их длина не зависит от данных. Всё, что собирается из выборок
    (record_ids, masters, truly_gone, instock_record_ids...), обязано идти
    через _id_filter.
    """
    tree = ast.parse(TASKS_PATH.read_text(encoding="utf-8"))

    # Единственное законное место голых in_/not_in — сам fallback в _id_filter.
    allowed_spans: list[tuple[int, int]] = [
        (node.lineno, node.end_lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_id_filter"
    ]
    assert allowed_spans, "_id_filter пропал из notification_tasks.py"

    offenders = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("in_", "not_in")
        ):
            continue
        if any(lo <= node.lineno <= hi for lo, hi in allowed_spans):
            continue
        if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
            continue  # литерал фиксированного размера — безопасен
        offenders.append(f"строка {node.lineno}: {ast.unparse(node)[:100]}")

    assert not offenders, (
        "in_()/not_in() по python-списку в notification_tasks.py — это бинд на "
        "каждый элемент и падение на лимите asyncpg после обхода краулера. "
        "Используйте _id_filter:\n  " + "\n  ".join(offenders)
    )
