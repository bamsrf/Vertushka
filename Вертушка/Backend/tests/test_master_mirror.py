"""Зеркалирование мастеров: очередь, потолок, платный канал.

Зачем файл. Это первый канал, который копит обложки НАШИМИ силами, и у него
три способа тихо испортить жизнь: залезть в платный Discogs-бюджет, залипнуть
на мёртвой строке (как дрип 14.09) и незаметно нарастить счёт за хранилище.
Каждый закрыт здесь.
"""
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.tasks.master_mirror_tasks import _MAX_ATTEMPTS, mirror_master_covers_batch


@pytest.fixture()
def env(monkeypatch):
    def make(**vals):
        for var in ("MASTER_MIRROR_ENABLED", "MASTER_MIRROR_BATCH",
                    "MASTER_MIRROR_PACE_SEC", "MASTER_MIRROR_DAILY_CAP"):
            monkeypatch.delenv(var, raising=False)
        for k, v in vals.items():
            monkeypatch.setenv(k, str(v))
        return Settings(_env_file=None)
    return make


def test_defaults_are_conservative(env):
    """Дефолт обязан быть предсказуемым по деньгам.

    Каждый зеркалированный файл ложится в бакет НАВСЕГДА. 20 000/сутки при
    среднем файле ~100 КБ — это ~2 ГБ/сутки; поднять можно осознанно, когда
    посчитан тариф, а вот «случайно налить 85 ГБ за ночь» нельзя.
    """
    s = env()
    assert s.master_mirror_enabled is True
    assert s.master_mirror_daily_cap == 20000
    assert s.master_mirror_batch * 30 * 24 >= s.master_mirror_daily_cap, (
        "батч × прогоны в сутки должны упираться в потолок, а не наоборот"
    )


def test_batch_bounds(env):
    with pytest.raises(ValidationError):
        env(MASTER_MIRROR_BATCH=0)
    with pytest.raises(ValidationError):
        env(MASTER_MIRROR_BATCH=10_000)


def test_zero_cap_is_valid_kill_switch(env):
    """Потолок 0 — способ остановить накопление, не выкатывая код."""
    assert env(MASTER_MIRROR_DAILY_CAP=0).master_mirror_daily_cap == 0


@pytest.mark.asyncio
async def test_disabled_does_nothing(env, monkeypatch):
    monkeypatch.setenv("MASTER_MIRROR_ENABLED", "false")
    from app import config
    config.get_settings.cache_clear()
    try:
        assert await mirror_master_covers_batch() == {"skipped": "disabled"}
    finally:
        config.get_settings.cache_clear()


def test_paid_channel_excluded_from_queue():
    """source='discogs' не попадает в выборку.

    Картинки Discogs идут под дневной бюджет, зарезервированный под живых
    пользователей: фоновое накопление не имеет права его тратить, тем более
    что мастер с бесплатным источником закрывает ту же сетку артиста даром.
    """
    import inspect
    from app.tasks import master_mirror_tasks

    sql = inspect.getsource(master_mirror_tasks.mirror_master_covers_batch)
    # По ХОСТУ, а не по колонке source: 15.09.2026 оказалось, что source
    # описывает того, кто нашёл СТРОКУ, а не того, чья в ней картинка —
    # 9 215 строк с i.discogs.com были помечены caa/deezer/store/NULL.
    assert "cover_image_url NOT LIKE '%i.discogs.com%'" in sql


def test_queue_cannot_stall_on_one_row():
    """Predicate обязан учитывать счётчик попыток.

    Прямой вывод из аварии дрипа 14.09: одна строка, которую нельзя ни
    скачать, ни пометить, держала голову очереди сутки.
    """
    import inspect
    from app.tasks import master_mirror_tasks

    sql = inspect.getsource(master_mirror_tasks.mirror_master_covers_batch)
    assert "mirror_attempts < :max_att" in sql
    assert 1 < _MAX_ATTEMPTS <= 5


def test_bucket_head_treats_unknown_errors_as_present(monkeypatch):
    """Недоступность бакета не должна выглядеть как «файла нет».

    Иначе первая же сетевая икота превращает очередь в лавину повторных
    скачиваний с чужих CDN — и сжигает дневной потолок на файлы, которые у
    нас уже есть.
    """
    from app.services import s3_covers

    monkeypatch.setattr(s3_covers, "enabled", lambda: True)

    class _Boom:
        def head_object(self, **kw):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: _Boom())
    assert s3_covers.exists_sync("m1") is True


def test_bucket_head_reports_missing_on_404(monkeypatch):
    from app.services import s3_covers

    monkeypatch.setattr(s3_covers, "enabled", lambda: True)

    class _Missing:
        def head_object(self, **kw):
            raise RuntimeError("An error occurred (404) when calling HeadObject")

    monkeypatch.setattr(s3_covers, "_get_restore_client", lambda: _Missing())
    assert s3_covers.exists_sync("m1") is False


def test_bucket_head_is_false_when_s3_off(monkeypatch):
    """S3 выключен — вечного слоя нет, решение принимает диск."""
    from app.services import s3_covers

    monkeypatch.setattr(s3_covers, "enabled", lambda: False)
    assert s3_covers.exists_sync("m1") is False
