# План: Локальная БД — кэширование данных и обложек Discogs

## Цель
При добавлении записи в коллекцию — сохранять **все данные** (обложка, треклист, формат, метаданные) к себе в БД и на диск. Discogs нужен **только для новых запросов**. Это устраняет зависимость от нестабильных signed URL обложек Discogs (истекают через ~30 минут) и снижает количество API-запросов.

## Текущее состояние

### Что уже есть
- Таблица `records` хранит: title, artist, label, year, genre, style, format, tracklist (JSONB), discogs_data (JSONB), цены, barcode
- `cover_image_url` / `thumb_image_url` — хранят **signed URL из Discogs** (протухают через 30 мин)
- `get_or_create_record_by_discogs_id()` — уже сохраняет данные при первом запросе
- Redis — кэш для API-ответов Discogs (TTL 10 мин — 30 дней)
- nginx — proxy cache для публичных endpoints
- `uploads/avatars/` — уже есть механизм хранения файлов
- Продакшн: 4 uvicorn-воркера (`--workers 4`) + отдельный scheduler-контейнер
- Volume `uploads_data` смонтирован в контейнерах `api` и `scheduler`

### Проблема
- URL обложек Discogs — **signed, истекают через ~30 минут**
- При каждом открытии коллекции мобилка получает мёртвые URL
- Для обновления URL нужен новый запрос к Discogs API (тратится rate limit)
- Нет локального хранения обложек

---

## Архитектура решения

### Принцип: 3 уровня хранения изображений

| Уровень | Что хранится | Когда сохраняется | Удаляется ли |
|---------|-------------|-------------------|--------------|
| 1. Данные записи | PostgreSQL (title, tracklist, JSONB...) | При первом запросе discogs_id | Никогда |
| 2. Обложка Discogs | Файл на диске `uploads/covers/{discogs_id}.jpg` | При добавлении в коллекцию/вишлист | LRU при нехватке места |
| 3. Фото пользователя | Файл на диске `uploads/user_photos/{user_id}/{uuid}.jpg` | Загрузка пользователем | По запросу пользователя |

### Логика отдачи обложки клиенту

```
GET /covers/{discogs_id}     ← ВАЖНО: отдельный prefix, НЕ под /api/

1. nginx проверяет файл uploads/covers/{discogs_id}.jpg → отдаёт статику (ETag + Last-Modified)
2. Файла нет → @covers_fallback → FastAPI:
   a. Запись с discogs_id есть в БД?
      → Запускаем фоновое скачивание (с Redis-lock дедупликацией)
      → Возвращаем 302 redirect на cover_image_url (signed Discogs URL из БД)
      → Если cover_image_url пуст — возвращаем 404
   b. Записи нет → 404
```

---

## Этапы реализации

### Этап 1: Локальное хранение обложек (Backend)

#### 1.1 Новые поля в модели `Record`
Файл: `Backend/app/models/record.py`

```python
# Добавить 2 поля (НЕ 3 — cover_last_accessed убран, см. обоснование ниже):
cover_local_path: Mapped[str | None]       # путь к файлу: "covers/12345.jpg"
cover_cached_at: Mapped[datetime | None]    # когда скачали (используется для LRU-порядка)
```

> **Почему нет `cover_last_accessed`**: nginx раздаёт обложки как статику — FastAPI
> не получает запросов на чтение, поле никогда не обновится. Для LRU используем
> `cover_cached_at` — старейшие обложки удаляются первыми. Это не идеальный LRU,
> но достаточный для текущего масштаба.

#### 1.2 Alembic миграция
Файл: `Backend/alembic/versions/YYYYMMDD_add_cover_local_fields.py`
- Добавить 2 колонки (`cover_local_path`, `cover_cached_at`) в таблицу `records`

#### 1.3 Сервис скачивания обложек
Файл: `Backend/app/services/cover_storage.py` (новый)

```python
class CoverStorageService:
    COVERS_DIR = "uploads/covers"
    MAX_CACHE_SIZE_MB = 5000  # 5 ГБ по умолчанию (настраивается)

    async def download_and_store(self, discogs_id: str, image_url: str, db: AsyncSession) -> str | None:
        """
        Скачивает обложку из Discogs, сохраняет на диск, обновляет запись в БД.

        Важные детали реализации:
        1. Redis lock: SET cover_download:{discogs_id} NX EX 60
           — предотвращает параллельное скачивание одной обложки
           — обязательно, т.к. в проде 4 uvicorn-воркера (отдельные процессы)
           — если lock не получен — return None (другой воркер уже скачивает)
        2. Конвертация формата: img.convert('RGB').save(..., format='JPEG', quality=85)
           — Discogs может вернуть PNG/WebP с alpha-каналом
        3. Атомарная запись: tmp-файл в uploads/covers/.tmp_{discogs_id}_{uuid4()}.jpg
           → os.rename() в uploads/covers/{discogs_id}.jpg
           — оба файла на одном volume = rename атомарен
        4. После rename: UPDATE records SET cover_local_path, cover_cached_at WHERE discogs_id = ...
        5. Finally: удалить Redis lock
        """

    async def get_cover_path(self, discogs_id: str) -> str | None:
        """Возвращает путь к локальной обложке или None."""

    async def cleanup_lru(self, target_size_mb: int, db: AsyncSession) -> int:
        """
        Удаляет самые старые обложки до достижения target_size_mb.

        ВАЖНО: в одной транзакции:
        1. SELECT records WHERE cover_local_path IS NOT NULL ORDER BY cover_cached_at ASC LIMIT N
        2. Удалить файлы с диска
        3. UPDATE records SET cover_local_path = NULL, cover_cached_at = NULL WHERE id IN (...)
        4. COMMIT

        Если файл уже удалён (ручное удаление / другой процесс) — просто обнулить БД-поля.
        Возвращает кол-во удалённых.
        """

    async def get_cache_stats(self) -> dict:
        """Размер кэша, количество файлов."""
```

Детали:
- Скачивать **medium (500px)** — достаточно для мобилки, ~80-150 КБ
- Формат файла: `uploads/covers/{discogs_id}.jpg`
- При скачивании: resize до 500px max side через Pillow
- **Конвертация**: `Image.open(buf).convert('RGB').save(tmp_path, format='JPEG', quality=85)` — обрабатывает PNG с прозрачностью, WebP, и др.
- Обработка ошибок: если Discogs вернул 403/404 — не крашить, просто оставить `cover_local_path = None`
- **Tmp-файл**: всегда в `uploads/covers/.tmp_*` (тот же каталог = тот же volume → `os.rename` атомарен)

#### 1.4 API endpoint для обложек
Файл: `Backend/app/api/covers.py` (новый)

```
GET /covers/{discogs_id}
→ FastAPI получает запрос ТОЛЬКО если nginx не нашёл файл (@covers_fallback)
→ Запись есть в БД?
  → ДА: запускаем ensure_cover_cached() в фоне + 302 redirect на cover_image_url
  → НЕТ: 404

POST /covers/{discogs_id}/refresh
→ Требует авторизацию: X-Internal-Token из env (INTERNAL_API_TOKEN)
→ Принудительно перекачать обложку из Discogs
→ Удалить старый файл, скачать заново, обновить cover_cached_at
```

> **Авторизация /refresh**: В проекте нет admin-ролей. Используем header
> `X-Internal-Token` сверяемый с env `INTERNAL_API_TOKEN`. Достаточно для
> internal-only endpoint. Если в будущем появятся admin-роли — мигрировать.

#### 1.5 Раздача статики через nginx
Файл: `Backend/nginx/nginx.conf` — добавить:

```nginx
# Обложки — ОТДЕЛЬНЫЙ prefix /covers/ (НЕ под /api/)
# Используем root + try_files (НЕ alias — у alias баг с try_files в nginx)
location /covers/ {
    root /app/uploads;                              # файл: /app/uploads/covers/{discogs_id}.jpg
    expires 7d;
    add_header Cache-Control "public";
    add_header ETag $upstream_http_etag;             # для cache invalidation на клиенте
    try_files $uri @covers_fallback;
}

location @covers_fallback {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

> **Почему НЕ `alias`**: `alias` + `try_files` — известный баг nginx, путь
> резолвится некорректно. `root` + отдельный prefix `/covers/` решает проблему.
>
> **Почему `expires 7d`, а не `30d immutable`**: обложки могут обновляться через
> `/refresh`. `7d` + ETag — клиент проверит при следующем запросе.

Файл: `Backend/docker-compose.prod.yml` — добавить volume в nginx:

```yaml
nginx:
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - ./certbot/conf:/etc/letsencrypt:ro
    - ./certbot/www:/var/www/certbot:ro
    - nginx_cache:/var/cache/nginx
    - uploads_data:/app/uploads:ro          # ← ДОБАВИТЬ: nginx раздаёт обложки
```

#### 1.6 Функция `ensure_cover_cached()` (отдельно от `get_or_create_record`)
Файл: `Backend/app/services/cover_storage.py`

```python
async def ensure_cover_cached(record: Record, db: AsyncSession) -> None:
    """
    Проверяет, есть ли локальная обложка. Если нет — запускает скачивание.
    Вызывать ТОЛЬКО из endpoint'ов добавления в коллекцию/вишлист.

    НЕ вызывается из get_or_create_record_by_discogs_id() —
    чтобы не создавать шквал скачиваний при импорте или обогащении данных.
    """
    if record.cover_local_path:
        return  # уже есть
    if not record.cover_image_url:
        return  # нечего скачивать
    asyncio.create_task(_download_with_lock(record.discogs_id, record.cover_image_url, db))
```

Вызов из endpoint'ов:
- `Backend/app/api/collections.py` — после `get_or_create_record_by_discogs_id()` + `db.add(item)`
- `Backend/app/api/wishlists.py` — аналогично

> **Почему отдельно от `get_or_create`**: эта функция вызывается из 3+ мест
> (коллекции, вишлисты, просмотр по discogs_id). Если встроить скачивание
> внутрь — будет неконтролируемый trigger. При массовом импорте это создаст
> шквал запросов к Discogs.

#### 1.7 Рефакторинг: убрать дублирование в `records.py`
Файл: `Backend/app/api/records.py`

Endpoint `get_record_by_discogs_id` (строки 381-452) дублирует логику
`get_or_create_record_by_discogs_id`. Рефакторнуть — использовать
`get_or_create_record_by_discogs_id` внутри.

#### 1.8 Сериализация `cover_url` в ответах API
Файл: `Backend/app/schemas/record.py`

Добавить computed-поле в `RecordResponse` и `RecordBrief`:

```python
cover_url: str | None = None  # заполняется в endpoint'е
```

Логика заполнения (в endpoint'е, не в схеме):
```python
if record.cover_local_path:
    response.cover_url = f"/covers/{record.discogs_id}"
    # Добавить ?v= для cache-busting при обновлении
    if record.cover_cached_at:
        response.cover_url += f"?v={int(record.cover_cached_at.timestamp())}"
else:
    response.cover_url = record.cover_image_url  # fallback на signed Discogs URL
```

> `cover_image_url` и `thumb_image_url` сохраняются в БД как есть (для fallback).
> Мобилка переходит на `cover_url`.

#### 1.9 Настройки
Файл: `Backend/app/config.py` — добавить:

```python
covers_dir: str = Field(default="uploads/covers", alias="COVERS_DIR")
covers_max_cache_mb: int = Field(default=5000, alias="COVERS_MAX_CACHE_MB")
internal_api_token: str = Field(default="", alias="INTERNAL_API_TOKEN")
```

#### 1.10 Роутер
Файл: `Backend/app/main.py` — зарегистрировать роутер:

```python
from app.api import covers
app.include_router(covers.router, prefix="/covers", tags=["Обложки"])
```

> **Prefix `/covers`**, не `/api/covers` — чтобы nginx `location /covers/`
> работал корректно с `root` директивой.

---

### Этап 2: Миграция существующих записей

#### 2.1 Скрипт миграции
Файл: `Backend/scripts/migrate_covers.py`

```python
"""
Скачивает обложки для всех записей, которые есть в коллекциях/вишлистах.
Запускать: python -m scripts.migrate_covers
Батчами по 50, с задержкой 1с между батчами (respect rate limit).
"""
```

Логика:
1. SQL-запрос с **дедупликацией по discogs_id**:
```sql
SELECT DISTINCT r.discogs_id, r.cover_image_url
FROM records r
WHERE r.cover_local_path IS NULL
  AND r.discogs_id IS NOT NULL
  AND (EXISTS (SELECT 1 FROM collection_items ci WHERE ci.record_id = r.id)
       OR EXISTS (SELECT 1 FROM wishlist_items wi WHERE wi.record_id = r.id))
```
2. Для каждой: запросить свежий URL из Discogs API → скачать → сохранить
3. Батч по 50 записей, пауза 1 секунда между батчами
4. Прогресс-бар, логирование, возможность продолжить с прерванного места (WHERE cover_local_path IS NULL)

> **Почему DISTINCT**: одна пластинка может быть в коллекциях нескольких
> пользователей и в вишлисте одновременно. Без дедупликации — дублирующие
> скачивания, трата rate limit.

#### 2.2 Cron для LRU-очистки
Добавить как APScheduler job в scheduler-контейнере (уже есть инфраструктура в `main.py`):

```python
# В main.py, рядом с другими scheduler jobs:
from app.services.cover_storage import CoverStorageService

async def cleanup_covers():
    async with async_session_maker() as db:
        service = CoverStorageService()
        deleted = await service.cleanup_lru(settings.covers_max_cache_mb, db)
        if deleted:
            logger.info("LRU cleanup: deleted %d covers", deleted)

scheduler.add_job(cleanup_covers, 'cron', hour=3, minute=0, id='covers_lru_cleanup')
```

> Не crontab — используем APScheduler, который уже работает в scheduler-контейнере.

---

### Этап 3: Таблица пользовательских фото (будущее)

#### 3.1 Модель `UserRecordPhoto`
Файл: `Backend/app/models/user_photo.py` (новый)

```python
class UserRecordPhoto(Base):
    __tablename__ = "user_record_photos"

    id: UUID (PK)
    user_id: UUID (FK → users.id)
    collection_item_id: UUID (FK → collection_items.id)
    photo_path: str            # "user_photos/{user_id}/{uuid}.jpg"
    is_primary: bool = False   # показывать вместо обложки Discogs
    created_at: datetime
```

#### 3.2 API для загрузки фото
```
POST /api/collections/{id}/items/{item_id}/photos
→ Принимает multipart/form-data
→ Resize до 800px, JPEG quality 85
→ img.convert('RGB') — обработка PNG/WebP
→ Сохраняет в uploads/user_photos/{user_id}/{uuid}.jpg

DELETE /api/collections/{id}/items/{item_id}/photos/{photo_id}

PATCH /api/collections/{id}/items/{item_id}/photos/{photo_id}
→ { "is_primary": true }
```

---

### Этап 4: Обновление Mobile

#### 4.1 Обновить URL обложек в API клиенте
Файл: `Mobile/lib/api.ts`

Добавить хелпер:
```typescript
function getCoverUrl(record: VinylRecord | CollectionItem['record']): string | undefined {
  // 1. Если есть cover_url от бэкенда (новое поле) — используем его
  if (record.cover_url) {
    return resolveMediaUrl(record.cover_url);  // resolveMediaUrl уже есть в api.ts
  }
  // 2. Fallback на старые поля (для записей без локальной обложки)
  return record.cover_image_url || record.thumb_image_url || undefined;
}
```

Файл: `Mobile/lib/types.ts` — добавить поле:
```typescript
// В интерфейсы VinylRecord, RecordSearchResult, и др.:
cover_url?: string;
```

#### 4.2 Обновить компонент RecordCard
Файл: `Mobile/components/RecordCard.tsx`
- Заменить `record.cover_image_url || record.thumb_image_url` на `getCoverUrl(record)`
- `expo-image` с `cachePolicy="disk"` продолжит работать
- `?v={timestamp}` в URL обеспечивает cache-busting при обновлении обложки

---

## Объём хранилища (прогноз)

| Компонент | На 1 запись | На 10к записей | На 100к записей |
|-----------|------------|----------------|-----------------|
| PostgreSQL данные | ~4 КБ | ~40 МБ | ~400 МБ |
| Обложка 500px | ~100 КБ | ~1 ГБ | ~10 ГБ |
| Пользовательское фото | ~200 КБ | - | - |

**Рекомендация**: для старта хватит 20 ГБ свободного места на сервере.

---

## Конфигурация (env переменные)

```env
# Хранение обложек
COVERS_DIR=uploads/covers           # директория для обложек
COVERS_MAX_CACHE_MB=5000            # макс размер кэша обложек (МБ)
INTERNAL_API_TOKEN=<random-secret>  # токен для /covers/{id}/refresh
```

---

## Риски и митигация

| Риск | Вероятность | Митигация |
|------|------------|-----------|
| Discogs rate limit при массовой миграции | Высокая | Батчи по 50, пауза 1с, приоритет BATCH |
| Диск переполнится обложками | Средняя | LRU-очистка через APScheduler, мониторинг, COVERS_MAX_CACHE_MB |
| Обложка не скачалась (403/timeout) | Средняя | Self-healing: GET /covers/ fallback запускает повторное скачивание |
| Discogs изменил формат API | Низкая | raw `discogs_data` JSONB как страховка |
| Два воркера скачивают одну обложку | Средняя | **Redis lock** `SET cover_dl:{discogs_id} NX EX 60` + атомарная запись (tmp+rename в одном каталоге) |
| PNG/WebP от Discogs сохраняется как JPEG некорректно | Средняя | `img.convert('RGB').save(format='JPEG')` — принудительная конвертация |
| LRU-очистка удаляет файлы, БД рассинхрон | Высокая | cleanup_lru() обновляет PostgreSQL в одной транзакции с удалением |
| nginx не видит uploads volume | Высокая | `uploads_data:/app/uploads:ro` в docker-compose nginx volumes |

---

## Порядок работы

```
⬜ Этап 1 (обязательный): Локальное хранение обложек
   1.1  Миграция БД (2 новых поля: cover_local_path, cover_cached_at)
   1.2  CoverStorageService (Redis lock, конвертация, атомарная запись, LRU с БД-синхронизацией)
   1.3  API endpoint /covers/ (GET с self-healing, POST /refresh с X-Internal-Token)
   1.4  nginx: location /covers/ с root (НЕ alias), ETag, try_files → @fallback
   1.5  docker-compose: uploads_data volume в nginx
   1.6  ensure_cover_cached() — вызов из collections/wishlists (НЕ из get_or_create)
   1.7  Рефакторинг: убрать дублирование в records.py get_record_by_discogs_id
   1.8  cover_url в RecordResponse/RecordBrief + cache-busting ?v=timestamp
   1.9  Настройки конфига (COVERS_DIR, COVERS_MAX_CACHE_MB, INTERNAL_API_TOKEN)
   1.10 Роутер /covers в main.py

⬜ Этап 2: Миграция существующих записей
   2.1 Скрипт migrate_covers.py (DISTINCT по discogs_id)
   2.2 APScheduler job для LRU-очистки (не crontab)

⬜ Этап 3 (будущее): Пользовательские фото
   3.1 Модель + миграция
   3.2 API загрузки

⬜ Этап 4: Обновление Mobile
   4.1 cover_url в types.ts + getCoverUrl() хелпер
   4.2 Обновить RecordCard
```

---

## Что НЕ меняется
- Redis остаётся как есть (кэш API-ответов Discogs для поиска)
- Таблица `records` — структура данных не меняется (только 2 новых поля)
- Поиск по-прежнему идёт через Discogs API (кэшируется Redis + nginx)
- `discogs_data` JSONB — хранит полный ответ Discogs как страховку
- `cover_image_url` / `thumb_image_url` — сохраняются для fallback, мобилка переходит на `cover_url`
