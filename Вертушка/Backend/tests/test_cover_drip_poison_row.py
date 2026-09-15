"""Ядовитая строка не должна замораживать очередь дрипа.

Зачем файл. 14–15.09.2026 дрип простоял больше суток с нулём прогретых
обложек: релиз 37511514 был удалён из Discogs после выгрузки дампа, API
отдавал на него 404, а код считал ЛЮБОЕ исключение временным — строку не
помечал и выходил из прогона. Выборка кандидатов детерминированная
(ORDER BY year DESC), поэтому следующий прогон через минуту брал ту же строку.
Главный канал добора обложек был мёртв, и наружу это выглядело только как
одинаковая WARNING-строка раз в минуту.

Здесь фиксируется разделение ответов: «такого релиза нет» закрывает строку,
«сеть моргнула» — нет, но и очередь не держит дольше _TRANSIENT_FAIL_LIMIT.
"""
import httpx

from app.tasks.cover_drip_tasks import _is_permanent, _TRANSIENT_FAIL_LIMIT


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.discogs.com/releases/1")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


def test_404_is_permanent():
    """Релиз удалён из Discogs — ответ окончательный, строку закрываем.

    Ровно этот случай (37511514) и заморозил очередь.
    """
    assert _is_permanent(_status_error(404)) is True


def test_410_and_400_are_permanent():
    for code in (400, 410, 422):
        assert _is_permanent(_status_error(code)) is True, code


def test_auth_errors_are_not_permanent():
    """401/403 — про НАШ токен, а не про строку.

    Если считать их окончательными, протухший ключ за ночь пометит
    проверенными миллионы строк, которые никто не спрашивал, — и дамп
    больше никогда не догреется.
    """
    for code in (401, 403):
        assert _is_permanent(_status_error(code)) is False, code


def test_429_is_not_permanent():
    """Прямое «притормози» — этим занимается headroom-гейт, не карантин."""
    assert _is_permanent(_status_error(429)) is False


def test_server_errors_and_network_are_not_permanent():
    assert _is_permanent(_status_error(500)) is False
    assert _is_permanent(_status_error(503)) is False
    assert _is_permanent(httpx.ConnectTimeout("timeout")) is False
    assert _is_permanent(TimeoutError()) is False


def test_quarantine_limit_is_finite_and_small():
    """Карантин обязан существовать и срабатывать быстро.

    Он — второй рубеж: ловит то, что не опознано как permanent (например,
    падение внутри парсинга ответа). Без него любая незакрывающаяся ошибка
    снова превращается в вечную голову очереди.
    """
    assert 1 < _TRANSIENT_FAIL_LIMIT <= 5
