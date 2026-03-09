# Вертушка — Реестр багов

Все баги проверены по коду. Пути файлов относительны корня `Вертушка/`.

---

## 🔴 Критические (поломающие функционал)

### 1. RecordCard — bare text в View (креш на iOS)
**Файл:** `Mobile/components/RecordCard.tsx:157–178`

`{record.year && (<Text>...</Text>)}` — если `record.year === 0` (число), выражение short-circuit'ит в `0`, который рендерится как голый текст внутри `<View>`. React Native крешится.
Тот же паттерн повторяется на строках 163, 169, 175 (dot-separator).

Триггер: коллекция. `CollectionItem.record.year` может быть `0` если запись в БД создалась без года.

```tsx
// RecordCard.tsx:158 — если year === 0, рендерит "0"
{record.year && (
  <Text style={styles.metaText}>{record.year}</Text>
)}
```

**Фикс:** заменить `record.year &&` на `record.year != null &&` (или `!!record.year`). Аналогично для всех dot-условий.

---

### 2. Год-фильтр отправляет одно число вместо диапазона
**Файл:** `Mobile/app/(tabs)/search.tsx:431`

```tsx
const yearValue = option.value && 'min' in option
  ? Math.floor((option.min! + option.max!) / 2)
  : undefined;
```

YEAR_OPTIONS (`search.tsx:71–81`):
| Опция | min | max | Отправляется year= |
|---|---|---|---|
| 2020-е | 2020 | 2029 | 2024 |
| 1960-е | 1960 | 1969 | 1964 |
| 1950-е и ранее | 0 | 1959 | **979** |

Discogs `year` — точный фильтр по одному году. Все декада-опции возвращают результаты ровно за один год.

**Фикс:** использовать `year_min` и `year_max` параметры в запросе (Discogs API их поддерживает). Бэкенд (`records.py`) тоже нужно обновить.

---

### 3. price_max всегда null
**Файл:** `Backend/app/services/discogs.py:249–258`

```python
price_min = stats_response.get("lowest_price", {}).get("value")
price_median = stats_response.get("median_price", {}).get("value")
# highest_price не извлекается вообще
```

`price_max` инициализируется `None` на строке 250 и никогда не перезаписывается.
На экране деталей пластинки поле "Макс." всегда пустое.

**Фикс:** добавить `price_max = stats_response.get("highest_price", {}).get("value")`.

---

### 4. Запрос на несуществующий endpoint (public wishlist URL)
**Файл:** `Mobile/lib/api.ts:497`

```ts
// Клиент делает:
const response = await this.client.get<{ url: string }>('/wishlists/public-url');

// Бэкенд имеет:
@router.post("/generate-link")  // wishlists.py:367
```

Два разногласия: метод (`GET` vs `POST`) и путь (`/public-url` vs `/generate-link`).
Любой вызов `getPublicWishlistUrl()` — гарантированный 404.

**Фикс:** изменить на `this.client.post(...)` и путь на `/wishlists/generate-link`.

---

### 5. Каждая страница деталей из поиска — два запроса, первый падает
**Файл:** `Mobile/app/record/[id].tsx:142–148`

```tsx
try {
  data = await api.getRecord(id);           // FastAPI: record_id: UUID → 422 на Discogs ID
} catch {
  data = await api.getRecordByDiscogsId(id); // fallback — правильный запрос
}
```

При навигации из поиска `id` — всегда Discogs ID (числовая строка). Первый запрос всегда даёт 422. Catch отлавливает и делает второй.

**Фикс:** определять формат `id` перед запросом (UUID regex) и сразу вызывать нужный метод.

---

### 6. move_to_collection — обращение к объекту после удаления из сессии
**Файл:** `Backend/app/api/wishlists.py:532–550`

```python
await db.delete(item)          # 532 — удаляем WishlistItem
await db.commit()              # 536 — коммит, item оторван от сессии
...
return CollectionItemResponse(
    ...
    record=item.record         # 550 — item уже DetachedInstance
)
```

`item.record` загружен через `selectinload`, в большинстве случаев будет в identity map, но после `commit()` объект формально detached. Может кинуть `DetachedInstanceError`.

**Фикс:** сохранить `item.record` в переменную до `db.delete(item)`, либо загрузить record отдельно через `collection_item`.

---

## 🟠 Серьёзные (влияют на работу)

### 7. Artist masters — лишние запросы к Discogs + неверный total
**Файл:** `Backend/app/services/discogs.py:706–735`

Обложки загружаются параллельно (`asyncio.gather`, строка 710), но суммарно это 1 запрос на список + N запросов на обложки = N+1 запросов к Discogs за один эндпоинт. При большом количестве мастер-релизов легко упереться в rate limit (429).

```python
total=len(results),  # 732 — количество на ТЕКУЩЕЙ странице после фильтрации
```

Клиент видит `total` = количество на странице, а не по всему артисту. Пагинация ломается.

**Фикс для total:** передать `pagination.get("pages")` или реальный `total` из Discogs ответа. Для обложек — рассмотреть кэширование или использование `thumb` из списка.

---

### 8. Пагинация артиста — жёсткая константа 20
**Файл:** `Mobile/app/artist/[id].tsx:75`

```tsx
setHasMore(data.results.length === 20);
```

Бэкенд фильтрует по `role === "Main"`, поэтому на странице может быть любое число результатов < 20. Если пришло 15 из 50 total — пагинация останавливается.

**Фикс:** использовать `data.total` и текущее суммарное количество загруженных для определения `hasMore`. Бэкенд должен вернуть корректный `total` (см. баг 7).

---

### 9. Race condition при создании Record
**Файл:** `Backend/app/api/records.py:31–87`

`get_or_create_record_by_discogs_id`: SELECT → если нет → INSERT. Без блокировки или обработки unique constraint на `discogs_id`. Два одновременных запроса на одну пластинку → второй INSERT упадёт с `IntegrityError` → 500.

**Фикс:** обернуть INSERT в `try/except IntegrityError`, в catch повторить SELECT.

---

### 10. isRefreshing = isLoading на экране коллекции
**Файл:** `Mobile/app/(tabs)/collection.tsx:281`

```tsx
isRefreshing={isLoading}
```

`isLoading` — общий флаг стора (`store.ts:325`). Он `true` при начальной загрузке, при смене табов, при любом fetch. Индикатор pull-to-refresh крутится при каждой загрузке, а не только при явном pull.

**Фикс:** добавить отдельный `isRefreshing` стейт в компоненте, выставлять его только в `handleRefresh`.

---

### 11. Экран мастер-релиза без Header при загрузке и ошибке
**Файл:** `Mobile/app/master/[id]/index.tsx:75–89`

```tsx
if (isLoading) {
  return (
    <View style={styles.loadingContainer}>  // нет Header, нет SafeArea
      <ActivityIndicator ... />
    </View>
  );
}
```

На iOS нельзя вернуться назад (кроме свайпа от края). Для сравнения — на экране артиста (`artist/[id].tsx:98`) `<Header title="Артист" showBack />` есть в обоих состояниях.

**Фикс:** добавить `<Header title="Мастер-релиз" showBack />` в оба ранних return (loading и error).

---

## Приоритет работы

| # | Баг | Приоритет | Оценка сложности |
|---|---|---|---|
| 1 | RecordCard bare text (креш) | P0 | Простая |
| 4 | GET /public-url → 404 | P0 | Простая |
| 3 | price_max null | P1 | Простая |
| 5 | Double-request на record detail | P1 | Простая |
| 6 | move_to_collection detached | P1 | Средняя |
| 2 | Year-filter → single year | P1 | Средняя |
| 9 | Race condition Record create | P1 | Средняя |
| 10 | isRefreshing = isLoading | P2 | Простая |
| 11 | Master detail no header | P2 | Простая |
| 7 | Artist masters N+1 + total | P2 | Средняя |
| 8 | Artist pagination const 20 | P2 | Простая (зависит от 7) |
