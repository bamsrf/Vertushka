"""Сторож свободного места.

Зачем он появился: алертов в проекте хватало — покрытие обложек, доля ошибок,
квоты, штормы rate-limit, — но за диском не следил НИКТО. При этом кончившийся
диск ломает не картинки, а Postgres: база перестаёт писать, и это полноценная
авария. Узнать о ней по упавшему приложению — худший из способов.

Замер 18.08.2026: свободно 8.8 ГБ из 38, обложки прибавляют ~280 МБ в сутки на
одних фоновых джобах. Запас — около месяца.
"""
from collections import namedtuple

import pytest

from app.tasks import disk_tasks

_Usage = namedtuple("_Usage", "total used free")
_GB = 1024 ** 3


def _fake_disk(monkeypatch, free_gb: float, total_gb: float = 38.0):
    used = int((total_gb - free_gb) * _GB)
    monkeypatch.setattr(disk_tasks.shutil, "disk_usage",
                        lambda _p: _Usage(int(total_gb * _GB), used, int(free_gb * _GB)))
    monkeypatch.setattr(disk_tasks, "_dir_size_gb", lambda _p: 3.0)


@pytest.fixture
def fired(monkeypatch):
    calls = []
    monkeypatch.setattr(disk_tasks.alerts, "fire_and_forget",
                        lambda **kw: calls.append(kw))
    return calls


@pytest.mark.asyncio
async def test_healthy_disk_stays_quiet(monkeypatch, fired):
    """Молчание при норме — иначе алерт выучиваются игнорировать."""
    _fake_disk(monkeypatch, free_gb=8.8)
    snap = await disk_tasks.check_disk_space()
    assert snap["free_gb"] == 8.8
    assert not fired


@pytest.mark.asyncio
async def test_warns_before_it_burns(monkeypatch, fired):
    """Предупреждение — чтобы оставалось время на спокойное решение."""
    _fake_disk(monkeypatch, free_gb=5.0)
    await disk_tasks.check_disk_space()
    assert len(fired) == 1
    assert fired[0]["key"] == "disk_space_low"


@pytest.mark.asyncio
async def test_critical_uses_its_own_key(monkeypatch, fired):
    """Отдельный ключ обязателен: троттлинг в alerts общий по ключу, и
    предупреждение не должно заглушить критический алерт."""
    _fake_disk(monkeypatch, free_gb=1.0)
    await disk_tasks.check_disk_space()
    assert len(fired) == 1
    assert fired[0]["key"] == "disk_space_critical"
    assert fired[0]["key"] != "disk_space_low"


@pytest.mark.asyncio
async def test_alert_body_says_what_to_do(monkeypatch, fired):
    """Алерт без подсказки бесполезен в три часа ночи."""
    _fake_disk(monkeypatch, free_gb=1.0)
    await disk_tasks.check_disk_space()
    body = fired[0]["body"]
    assert "docker builder prune" in body
    assert "Postgres" in body


@pytest.mark.asyncio
async def test_unreadable_disk_does_not_crash_the_scheduler(monkeypatch, fired):
    """Джоба в планировщике не имеет права ронять цикл."""
    def boom(_p):
        raise OSError("нет доступа")
    monkeypatch.setattr(disk_tasks.shutil, "disk_usage", boom)
    assert await disk_tasks.check_disk_space() == {}
    assert not fired


def test_thresholds_leave_room_to_react():
    """Пороги должны давать время, а не констатировать факт.

    При замеренном темпе роста обложек ~0.28 ГБ/сутки предупреждение на 6 ГБ
    даёт три недели, критический на 2.5 ГБ — больше недели.
    """
    assert disk_tasks._WARN_FREE_GB > disk_tasks._CRIT_FREE_GB
    assert disk_tasks._CRIT_FREE_GB >= 2.0
