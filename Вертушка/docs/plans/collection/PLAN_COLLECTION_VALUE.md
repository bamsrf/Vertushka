# План: Стоимость коллекции винила

## Контекст

Добавляем оценку стоимости пластинок и всей коллекции. Данные по ценам уже приходят из Discogs API (`/marketplace/stats/{release_id}`) и сохраняются в модели Record (`estimated_price_min/max/median` в USD). Эндпоинт `GET /collections/{id}/stats` уже считает `total_estimated_value_min/max`.

**Ключевая идея**: USD — справочная цена (Discogs). При добавлении в коллекцию — цена пересчитывается в рубли (курс ЦБ × наценка 1.7x). В коллекции и на экране оценки — всё в рублях.

---

## Источники данных

### Цены пластинок — Discogs Marketplace API
- Эндпоинт: `GET /marketplace/stats/{release_id}`
- Возвращает: `lowest_price`, `highest_price`, `median_price` (USD)
- Уже реализовано в `Backend/app/services/discogs.py` → метод `_get_price_stats()`
- Цены кешируются в БД (модель Record) при первом запросе

### Курс валют — API Центрального Банка РФ
- Эндпоинт: `https://www.cbr-xml-daily.ru/daily_json.js`
- Неофициальное зеркало данных ЦБ РФ в JSON (официальный сайт отдаёт только XML)
- Бесплатный, без авторизации, без лимитов
- Обновляется ежедневно
- Пример ответа:
```json
{
  "Date": "2025-02-25T11:30:00+03:00",
  "Valute": {
    "USD": {
      "ID": "R01235",
      "CharCode": "USD",
      "Nominal": 1,
      "Name": "Доллар США",
      "Value": 92.5058
    }
  }
}
```

### Наценка для российского рынка
- Коэффициент: **1.7x** (доставка + таможня + маржа магазинов)
- Винил в РФ стоит примерно в 1.5–2x дороже чем на Discogs
- Формула: `price_rub = price_usd × usd_rub_rate × 1.7`

---

## Фаза 1: Backend — Курс ЦБ и расширение API

### 1.1 Сервис курса валют
**Новый файл:** `Backend/app/services/exchange.py`

- Запрос к `https://www.cbr-xml-daily.ru/daily_json.js`
- Кеш в памяти (TTL 6 часов) — курс обновляется раз в день
- `async get_usd_rub_rate() -> float`
- Fallback: последний кешированный курс → хардкод ~90₽

### 1.2 Конфигурация наценки
**Файл:** `Backend/app/config.py`

```python
RU_VINYL_MARKUP = 1.7
```

### 1.3 Расширение модели CollectionItem
**Файл:** `Backend/app/models/collection.py`

Добавить поле:
```python
estimated_price_rub = Column(Numeric(10, 2), nullable=True)
```
Рублёвая стоимость фиксируется на момент добавления в коллекцию.

### 1.4 Пересчёт в рубли при добавлении в коллекцию
**Файл:** `Backend/app/api/collections.py`

При `POST /collections/{id}/items`:
1. Берём `record.estimated_price_median` (USD)
2. Получаем курс: `await get_usd_rub_rate()`
3. Считаем: `median_usd × usd_rub_rate × RU_VINYL_MARKUP`
4. Сохраняем в `CollectionItem.estimated_price_rub`

### 1.5 Расширение CollectionStats
**Файл:** `Backend/app/schemas/collection.py`

Новые поля в `CollectionStats`:
```python
total_estimated_value_median: float | None   # сумма median USD по всем записям
total_estimated_value_rub: float | None      # сумма рублёвых оценок
usd_rub_rate: float | None                   # текущий курс ЦБ
ru_markup: float                             # коэффициент (1.7)
most_expensive: RecordBrief | None           # самая дорогая запись (по рублям)
most_expensive_price_rub: float | None       # её цена в рублях
records_with_price: int                      # сколько записей имеют цену
```

**Файл:** `Backend/app/api/collections.py`

Обновить `get_collection_stats()`:
- Суммировать `estimated_price_rub` по всем items
- Суммировать `estimated_price_median` (USD) по всем records
- Найти самую дорогую запись (по `estimated_price_rub`)
- Получить актуальный курс ЦБ
- Вернуть расширенную статистику

### 1.6 Сортировка коллекции по цене
**Файл:** `Backend/app/api/collections.py`

В `GET /collections/{id}` добавить query-параметр:
```
sort_by: str = "added_at"  # added_at | price_desc | price_asc
```
Сортировка по `CollectionItem.estimated_price_rub`.

### 1.7 Миграция существующих данных
- Alembic миграция для добавления колонки `estimated_price_rub`
- Скрипт пересчёта: для всех существующих CollectionItem посчитать рублёвую цену по текущему курсу

---

## Фаза 2: Mobile — API, типы, стор

### 2.1 Типы
**Файл:** `Mobile/lib/types.ts`

```typescript
interface CollectionStats {
  total_records: number;
  total_estimated_value_min: number | null;
  total_estimated_value_max: number | null;
  total_estimated_value_median: number | null;
  total_estimated_value_rub: number | null;
  usd_rub_rate: number | null;
  ru_markup: number;
  most_expensive: VinylRecord | null;
  most_expensive_price_rub: number | null;
  records_with_price: number;
  records_by_year: Record<number, number>;
  records_by_genre: Record<string, number>;
  oldest_record_year: number | null;
  newest_record_year: number | null;
}
```

Добавить в `CollectionItem`:
```typescript
estimated_price_rub: number | null;
```

### 2.2 API-клиент
**Файл:** `Mobile/lib/api.ts`

- `getCollectionStats(collectionId: string): Promise<CollectionStats>`
- Добавить параметр `sort_by` в запросы коллекции

### 2.3 Store
**Файл:** `Mobile/lib/store.ts`

В `useCollectionStore`:
```typescript
stats: CollectionStats | null;
fetchStats: (collectionId: string) => Promise<void>;
sortBy: 'added_at' | 'price_desc' | 'price_asc';
setSortBy: (sort: string) => void;
```

---

## Фаза 3: Mobile — UI

### 3.1 Кнопка оценки стоимости в коллекции
**Файл:** `Mobile/app/(tabs)/collection.tsx`

- Иконка `₽` (или банкноты) рядом с существующими фильтрами (формат, вид)
- При нажатии → навигация на экран оценки: `router.push('/collection/value')`

### 3.2 Экран оценки стоимости
**Новый файл:** `Mobile/app/collection/value.tsx`

Полноценный экран с навигацией назад. При открытии:

1. **Загрузка**: запрос `GET /collections/{id}/stats`
2. **Анимация шкалы**: горизонтальная полоска заполняется синим градиентом слева направо (~2 сек)
3. **Бегущие цифры**: числа крутятся от 0 до итоговой суммы ₽, замедляясь к финалу
4. **Технология**: `react-native-reanimated`
   - `useSharedValue` для прогресса (0 → 1)
   - `withTiming` с `Easing.out` для плавного замедления
   - `useDerivedValue` для интерполяции числа → текст с разделителями тысяч

**Содержимое экрана:**
- Заголовок: "Оценка стоимости"
- Шкала с анимацией заполнения
- Общая стоимость в ₽ (крупно, анимированные цифры)
- Справочно: стоимость в USD, курс ЦБ, наценка 1.7x
- Подпись: "Оценка по X из Y пластинок"
- Блок "Самая дорогая" — RecordCard с ценой в ₽
- FlatList: вся коллекция отсортированная по цене (от дорогих к дешевым)
- На каждой карточке видна цена в ₽

### 3.3 Рубли на карточках в коллекции
**Файл:** `Mobile/app/(tabs)/collection.tsx`

- На карточках коллекции показывать `estimated_price_rub` из CollectionItem
- Формат: `~XX XXX ₽` (с разделителями тысяч)

### 3.4 Регистрация роута
**Файл:** `Mobile/app/_layout.tsx`

- Добавить роут `collection/value`

---

## Файлы для изменения

| Файл | Действие |
|------|----------|
| `Backend/app/services/exchange.py` | **Создать** — сервис курса ЦБ |
| `Backend/app/config.py` | Добавить `RU_VINYL_MARKUP = 1.7` |
| `Backend/app/models/collection.py` | Добавить `estimated_price_rub` в CollectionItem |
| `Backend/app/schemas/collection.py` | Расширить `CollectionStats` |
| `Backend/app/api/collections.py` | Stats + сортировка + пересчёт при добавлении |
| `Mobile/lib/types.ts` | `CollectionStats` интерфейс, обновить `CollectionItem` |
| `Mobile/lib/api.ts` | `getCollectionStats()`, параметр `sort_by` |
| `Mobile/lib/store.ts` | Stats в collection store |
| `Mobile/app/collection/value.tsx` | **Создать** — экран оценки стоимости |
| `Mobile/app/(tabs)/collection.tsx` | Кнопка ₽, рубли на карточках |
| `Mobile/app/_layout.tsx` | Роут `collection/value` |

---

## Подводные камни

1. **Discogs rate limit**: цены кешируются в БД при первом запросе — массовый refetch не нужен. Но при большой коллекции (100+ записей) первый запрос stats может быть медленным
2. **Не у всех пластинок есть цена**: Discogs не возвращает цену для редких/непопулярных релизов. UI должен показывать "Оценка по X из Y записей"
3. **Курс ЦБ недоступен**: нужен fallback — последний кеш → хардкод. Также `cbr-xml-daily.ru` может быть недоступен из-за рубежа — на проде (РФ-сервер) проблем не будет
4. **Alembic миграция**: нужна для добавления колонки `estimated_price_rub` в `collection_items`
5. **Курс меняется**: рублёвая цена фиксируется на момент добавления. В будущем можно добавить кнопку "Пересчитать по актуальному курсу"
6. **Анимация на слабых устройствах**: использовать `react-native-reanimated` (UI thread), не JS-driven анимации

---

## Порядок реализации

1. Backend: `exchange.py` + конфиг
2. Backend: миграция модели + обновление API collections
3. Backend: тестирование эндпоинтов
4. Mobile: типы + API-клиент + стор
5. Mobile: экран оценки стоимости с анимацией
6. Mobile: кнопка ₽ в коллекции + рубли на карточках
7. Интеграционное тестирование

---

## Верификация

- [ ] `GET /collections/{id}/stats` возвращает `total_estimated_value_rub`, `most_expensive`, `usd_rub_rate`
- [ ] `POST /collections/{id}/items` сохраняет `estimated_price_rub` в CollectionItem
- [ ] Коллекция → кнопка ₽ → экран с анимацией шкалы и бегущими цифрами
- [ ] Самая дорогая пластинка отображается корректно
- [ ] Список коллекции сортируется по цене
- [ ] На карточках в коллекции видна цена в ₽
- [ ] Fallback при недоступном ЦБ работает корректно
- [ ] "Оценка по X из Y" корректно показывает сколько записей имеют цену
