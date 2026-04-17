# Bugfix Plan: Обложки, Фильтры, Скролл

> Дата: 2026-04-15
> Статус: Анализ завершён, правки не начаты
> Обновлено: 2026-04-15 — скорректировано после сверки с GitHub-версией и данными Discogs API

---

## Оглавление

1. [БАГ 1: Обложки отображаются как заглушки](#баг-1-обложки-отображаются-как-заглушки)
2. [БАГ 2: Фильтры — синглы в альбомах](#баг-2-фильтры--синглы-в-альбомах)
3. [БАГ 3: Скролл зависает](#баг-3-скролл-зависает)
4. [Порядок исправлений](#порядок-исправлений)

---

## БАГ 1: Обложки отображаются как заглушки

### Симптомы
На экране артиста большинство карточек релизов показывают placeholder (иконка пластинки) вместо обложки, даже когда обложка реально есть на Discogs.

### Что уже работает правильно

| Мера | Файл:строка | Статус |
|------|-------------|--------|
| Кэш версия `v13` | `discogs.py:992` | ✅ |
| Rate limiter timeout `120s` для ENRICHMENT/BATCH | `discogs.py:209` | ✅ |
| `asyncio.wait_for` убран из `_get_master_info` | `discogs.py:903-940` | ✅ |
| Batch Search API с пагинацией до 5 страниц | `discogs.py:1048-1067` | ✅ |
| Re-enrichment при cache hit для null-обложек | `discogs.py:994-1014` | ✅ |
| TTL_MASTER_INFO = 7 дней | `cache.py:29` | ✅ |

### Оставшиеся проблемы

#### 1. Search API не находит часть мастеров из-за имени артиста

**Файл:** `discogs.py:1046`

```python
artist_name = raw_items[0].get("artist", "") if raw_items else ""
```

Имя берётся из первого элемента `/artists/{id}/releases`. Для коллабораций (например `"FEVER RAY / RED HOT CHILI PEPPERS"`) Search API с `artist=Red Hot Chili Peppers` может не вернуть эти мастера → обложка = null.

**Решение:** использовать имя из `get_artist` (endpoint `/artists/{id}`), а не из первого релиза. Оно уже может быть в кэше.

#### 2. Результат с null-обложками кэшируется на 1 день

**Файл:** `discogs.py:1130`

Текущая архитектура self-healing (re-enrichment через `/masters/{id}` при cache hit). Дополнительных изменений не требуется.

### Итого по Bug 1

Архитектура получения обложек корректна. Единственная правка — брать `artist_name` из кэша артиста. Критичных поломок нет.

---

## БАГ 2: Фильтры — синглы в альбомах

### Симптомы
При выборе фильтра "Альбомы" в списке появляются синглы (например "Tippa My Tongue", "Black Summer") и EP.

### Проверка данных Discogs API (RHCP, artist_id=92476)

Ключевое открытие: **`/artists/{id}/releases` НЕ возвращает поле `format` для мастер-релизов**. Все 52 мастера RHCP приходят с пустым форматом. Это значит `_guess_release_type` всегда получает `None` и не может определить тип.

При этом **Search API возвращает точные форматы** в виде массива:

| Релиз | Search API `format` | Правильный тип |
|---|---|---|
| Tippa My Tongue | `['File', 'FLAC', 'Single']` | single |
| Black Summer | `['File', 'FLAC', 'Single']` | single |
| Unlimited Love | `['Vinyl', 'LP', 'Album']` | album |
| Return Of The Dream Canteen | `['Vinyl', 'LP', 'Album']` | album |
| Can't Stop | `['CD', 'Single']` | single |
| Californication | `['CD', 'Maxi-Single']` | ep |
| Never Is A Long Time | `['Vinyl', '7"']` | single (неявно) |

### Корневая причина (ЕДИНСТВЕННАЯ): Search API format не используется

**Файл:** `discogs.py:1057-1061`

```python
for sr in search_data.get("results", []):
    sid = str(sr.get("id", ""))
    cover = sr.get("cover_image")
    if sid and cover:
        search_covers[sid] = cover
```

Batch search **уже запрашивает** Search API для обложек. Ответ содержит массив `format` с точной классификацией — но он **игнорируется**. Извлекается только `cover_image`.

Метод `_release_type_from_formats()` (`discogs.py:1148`) **уже существует** и умеет работать с такими массивами, но **нигде не вызывается**.

Текущая цепочка определения типа (`discogs.py:1097-1101`):
```python
release_type = (
    self._guess_release_type(item.get("format"), item.get("title"))  # format=None → None
    or info.get("release_type")                                       # только для enriched → часто None
    or "album"                                                        # ← ВСЁ становится album
)
```

На GitHub (старая версия) было проще — `_guess_release_type` возвращал `"album"` как дефолт напрямую. Результат тот же: **все релизы считались альбомами**. Фильтры "работали" только потому, что всё попадало в одну категорию.

### Решение: 2 изменения в `get_artist_masters`

**Изменение 1** — собирать format из Search API (рядом с `search_covers`):

```python
search_covers: dict[str, str] = {}
search_formats: dict[str, list[str]] = {}   # ← ДОБАВИТЬ
# ...
for sr in search_data.get("results", []):
    sid = str(sr.get("id", ""))
    cover = sr.get("cover_image")
    fmt = sr.get("format", [])              # ← ДОБАВИТЬ
    if sid and cover:
        search_covers[sid] = cover
    if sid and fmt:                          # ← ДОБАВИТЬ
        search_formats[sid] = fmt            # ← ДОБАВИТЬ
```

**Изменение 2** — использовать `_release_type_from_formats` как приоритетный источник:

```python
release_type = (
    self._release_type_from_formats(search_formats.get(master_id, []), item.get("title"))
    or self._guess_release_type(item.get("format"), item.get("title"))
    or info.get("release_type")
    or "unknown"   # НЕ "album"
)
```

### Дополнительно: добавить `7"` как маркер сингла

В `_release_type_from_formats` (`discogs.py:1148`): Discogs-релизы формата `['Vinyl', '7"']` без явного "Single" не распознаются. 7-дюймовые пластинки — практически всегда синглы.

```python
# После проверки "single" в fmt_set:
if '7"' in fmt_set or "flexi-disc" in fmt_set:
    return "single"
```

### Code quality: substring match в `_guess_release_type`

**Файл:** `discogs.py:969`

```python
if "ep" in fmt or "mini" in fmt:
    return "ep"
```

`"ep" in "repress"` → True. Это баг в коде, но **не является причиной проблемы с фильтрами**, поскольку для мастер-релизов `format` всегда пустой. Тем не менее, стоит исправить на токенизацию для корректности:

```python
tokens = {t.strip().lower() for t in format_str.split(",")}
```

### Бамп кэша

После изменений бампнуть кэш до `v14` для сброса неправильных типов.

---

## БАГ 3: Скролл зависает

### Симптомы
При скролле вниз по списку релизов артиста скролл застревает и не продолжается.

### Корневая причина: `ScrollView` + `.map()` без виртуализации

**Файл:** `artist/[id].tsx:385-393`

```tsx
<View style={styles.releasesGrid}>
  {filteredMasters.map((master) => (
    <RecordCard key={master.master_id} record={master} ... />
  ))}
</View>
```

Все карточки рендерятся одновременно. При 100+ мастерах — 100+ `Image` компонентов монтируются сразу.

### Решение: замена на FlatList

```tsx
<FlatList
  data={filteredMasters}
  keyExtractor={(item) => item.master_id}
  numColumns={2}
  renderItem={renderItem}
  onEndReached={handleLoadMore}
  onEndReachedThreshold={0.5}
  ListHeaderComponent={headerComponent}
  ListFooterComponent={footerComponent}
  ListEmptyComponent={emptyComponent}
  removeClippedSubviews={true}
  maxToRenderPerBatch={10}
  windowSize={5}
/>
```

Дополнительно:
- `useCallback` для `renderItem` и `handleMasterPress` (иначе `memo` в RecordCard не работает)
- Убрать `handleScroll` — использовать `onEndReached` от FlatList

---

## Порядок исправлений

### Шаг 1: Фильтры (Bug 2) — Backend

**Файл:** `Backend/app/services/discogs.py`

1. В batch search loop — собирать `search_formats` из Search API (+3 строки)
2. В сборке результатов — добавить `_release_type_from_formats` первым в цепочку
3. Заменить дефолт `"album"` на `"unknown"`
4. Добавить `7"` в `_release_type_from_formats` как маркер сингла
5. (Code quality) Токенизация в `_guess_release_type`
6. Бампнуть кэш до `v14`

### Шаг 2: Обложки (Bug 1) — Backend

**Файл:** `Backend/app/services/discogs.py`

1. Брать `artist_name` из кэша артиста, а не из первого релиза

### Шаг 3: Скролл (Bug 3) — Mobile

**Файл:** `Mobile/app/artist/[id].tsx`

1. Заменить `ScrollView` + `.map()` на `FlatList` с `numColumns={2}`
2. `useCallback` для `renderItem` и хендлеров
3. Header/Filters/Sort вынести в `ListHeaderComponent`
4. Убрать `handleScroll` — использовать `onEndReached` от FlatList

---

## Затронутые файлы

| Файл | Баги | Изменения |
|------|------|-----------|
| `Backend/app/services/discogs.py` | 1, 2 | `search_formats` dict, `_release_type_from_formats` в цепочку, `7"` маркер, токенизация, artist_name из кэша |
| `Mobile/app/artist/[id].tsx` | 3 | ScrollView → FlatList, useCallback, убрать handleScroll |
