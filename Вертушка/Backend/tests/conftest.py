"""Общая настройка для smoke-тестов.

Тесты намеренно тонкие и не требуют живой БД/Redis — они бьют по чистым
функциям (pricing, нормализация текста, транслитерация). Чтобы импорт
модулей `app.*` не падал на конструировании Settings, проставляем
безопасные dummy-значения для env до первого импорта приложения.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DISCOGS_TOKEN", "test-token")
