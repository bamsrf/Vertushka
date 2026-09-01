# Plan: Smart Search — Умный поиск

## Аудит текущей архитектуры

### Полная цепочка поиска (от нажатия до результата)

```
Пользователь вводит текст → нажимает "Поиск"
         │
         ▼
search.tsx: handleSearch()
         │
    ┌────┴──────────────────────────────┐
    │ Promise.allSettled([              │
    │   search(trimmed),  ←── store    │
    │   searchUsers(trimmed), ←── store │
    │ ])                                │
    └────┬──────────────────────────────┘
         │
         ▼
store.ts: useSearchStore.search()
         │
    ┌────┴──────────────────────────────────────────┐
    │ 1. Проверяет useCacheStore (in-memory, TTL 5m) │
    │ 2. Если кэш пуст → Promise.all([              │
    │      hasFilters                                │
    │        ? api.searchReleases(q, filters, 1)     │
    │        : api.searchMasters(q, 1),              │
    │      api.searchArtists(q, 1, 10),  ← лимит 10 │
    │    ])                                          │
    │ 3. Сохраняет в useCacheStore                   │
    │ 4. Добавляет query в searchHistory (AsyncStorage) │
    └────┬──────────────────────────────────────────┘
         │
         ▼
api.ts: deduplicatedGet → axios GET
         │
         ▼
Backend records.py: endpoint → DiscogsService
         │
    ┌────┴──────────────────────────────────────┐
    │ DiscogsService._get():                     │
    │   1. circuit breaker check                 │
    │   2. token bucket rate limiter (55 tok,    │
    │      0.95/sec ≈ 57 req/min)                │
    │   3. Redis cache → DB search_cache →       │
    │      Discogs API GET /database/search      │
    │   4. Retry 429/503 (до 3 попыток)          │
    └────┬──────────────────────────────────────┘
         │
         ▼
search.tsx: рендер результатов
    - topArtist = artistResults[0]  ← ТОЛЬКО ПЕРВЫЙ
    - RecordGrid с results (masters/releases)
    - userResults (до 3 пользователей)
```

### Ключевые ограничения, которые нельзя нарушить

| Ограничение | Где | Почему критично |
|---|---|---|
| **Discogs rate limit: 60 req/min** | rate_limiter.py (capacity=55, refill=0.95/s) | Превышение → бан IP. Каждый новый параллельный запрос сжирает токен |
| **2 параллельных запроса на 1 поиск** | store.ts: `Promise.all([masters, artists])` | Уже расходуют 2 токена за один поиск пользователя |
| **Circuit breaker** | discogs.py: 5 ошибок подряд → 60s блокировка | Если suggest-эндпоинт будет дёргаться каждые 300ms → при ошибках ускорит open |
| **3 уровня кэша** | Redis → PostgreSQL search_cache → Discogs | Новые эндпоинты ДОЛЖНЫ использовать ту же цепочку, иначе кэш бесполезен |
| **`@` prefix = user search** | search.tsx:149 | Любое автодополнение не должно конфликтовать с переключением режима |
| **`useCacheStore` хранит артистов вместе с релизами** | store.ts:236-270 | Ключ кэша: `query|filters|page`. Менять формат = инвалидация всего кэша |
| **`handleSearch` вызывается только при нажатии кнопки** | search.tsx:212 + cooldown 500ms | Нет debounced-поиска при наборе текста |

### Что Discogs умеет сам (не нужно изобретать)

Протестировано на `/database/search?type=artist`:
- `q=Bitles` → The Beatles (fuzzy match)
- `q=Pnk Floyd` → Pink Floyd (fuzzy match)
- `q=Metali` → Metallica + Metalica (несколько вариантов)
- `q=Beatles` → The Beatles, Beatles Revival Band, и т.д. (множественные совпадения)

**Вывод:** Discogs нативно обрабатывает опечатки и возвращает множественные результаты. Проблема не в поиске — **проблема в том, что UI показывает только `artistResults[0]`** (строка 436 search.tsx).

---

## Что именно сломано

### Проблема 1: показывается только 1 артист

```ts
// search.tsx:435-436
// Показываем только самого релевантного артиста (первого в списке)
const topArtist = artistResults.length > 0 ? artistResults[0] : null;
```

Discogs вернул 10 артистов → стор сохранил 10 → UI показал 1.

### Проблема 2: при опечатке нет обратной связи

Пользователь ввёл "Bitles" → получил результаты "The Beatles" → не понимает, почему запрос "сработал" с ошибкой. Нет баннера "Показано по: The Beatles".

### Проблема 3: нет подсказок во время набора

Поиск стартует только по нажатию кнопки. Пока пользователь набирает, экран пустой (или показана история). Нет возможности увидеть "правильное написание" до отправки.

---

## Фазы реализации

### Фаза 1 — Показать всех найденных артистов (1-2 часа)

**Риск:** нулевой. Данные уже есть в сторе, меняем только рендер.

**Что менять:**

**search.tsx** — убрать `topArtist`, заменить на список:
```ts
// БЫЛО (строка 436):
const topArtist = artistResults.length > 0 ? artistResults[0] : null;

// СТАНЕТ:
const [showAllArtists, setShowAllArtists] = useState(false);
const visibleArtists = showAllArtists
  ? artistResults
  : artistResults.slice(0, 3);
```

Рендер (вместо блока строк 714-748):
```tsx
{artistResults.length > 0 && (
  <View>
    {/* Первый артист — крупная gradient-карточка (как сейчас) */}
    <TouchableOpacity onPress={() => handleArtistPress(artistResults[0])} ...>
      <LinearGradient ...> {/* существующий стиль topArtistCard */} </LinearGradient>
    </TouchableOpacity>

    {/* Остальные — компактный список */}
    {visibleArtists.slice(1).map((artist) => (
      <TouchableOpacity
        key={artist.artist_id}
        style={styles.secondaryArtistCard}
        onPress={() => handleArtistPress(artist)}
      >
        <Image ... />
        <Text>{artist.name}</Text>
        <Ionicons name="chevron-forward" ... />
      </TouchableOpacity>
    ))}

    {/* Кнопка "Ещё X артистов" */}
    {!showAllArtists && artistResults.length > 3 && (
      <TouchableOpacity onPress={() => setShowAllArtists(true)}>
        <Text>Ещё {artistResults.length - 3} артистов</Text>
      </TouchableOpacity>
    )}
  </View>
)}
```

**Новые стили** (добавить в StyleSheet):
```ts
secondaryArtistCard: {
  flexDirection: 'row',
  alignItems: 'center',
  backgroundColor: Colors.surface,
  borderRadius: BorderRadius.lg,
  padding: Spacing.md,
  marginBottom: Spacing.sm,
},
```

**Совместимость с кэшем:** не ломает. `useCacheStore` уже хранит весь массив `artistResults`. `showAllArtists` — локальный стейт компонента, не попадает в кэш.

**Совместимость с `clearResults`:** не ломает. `clearResults()` обнуляет `artistResults: []` → `visibleArtists` будет `[]` → ничего не рендерится.

---

### Фаза 2 — Увеличить лимит запрашиваемых артистов (5 минут)

**Риск:** минимальный, но нужно учесть rate limit.

**Текущее:** `api.searchArtists(query, 1, 10)` — 10 артистов.

**Предлагаемое:** `api.searchArtists(query, 1, 15)`.

**Почему не 20–50:**
- Rate limiter: каждый поиск расходует 2 токена (masters + artists). Увеличение `per_page` НЕ расходует дополнительные токены — это тот же 1 запрос, просто ответ больше.
- НО: больший `per_page` = тяжелее ответ Discogs → дольше latency. 15 — разумный компромисс.
- Кэш Redis: размер записи растёт, но незначительно (~1KB на артиста).

**Что менять:**

```ts
// store.ts, строка ~258:
api.searchArtists(query, 1, 15),
```

**Совместимость с кэшем:** ключ кэша на бэкенде строится через `search_cache_key(params)`, где `per_page` входит в params. Старый кэш для `per_page=10` останется, новые запросы будут кэшироваться с `per_page=15`. Конфликта нет — это разные ключи, старый кэш просто протухнет по TTL.

**Совместимость с `useCacheStore` на фронте:** ключ `${query}|${filters}|1` НЕ включает per_page артистов, т.к. это параллельный запрос. Но `searchResult` содержит `artistResults` → новые результаты перезапишут кэш при первом запросе. Конфликта нет.

---

### Фаза 3 — Автодополнение (suggestions) (2–3 дня)

**Риск: СРЕДНИЙ** — главная угроза rate limit'у Discogs.

#### Расчёт нагрузки на rate limiter

Текущая ситуация:
- Пользователь делает ~1 поиск за 5-10 секунд
- Каждый поиск = 2 запроса к Discogs (masters + artists)
- Rate limiter: 55 токенов, refill 0.95/sec

С автодополнением (debounce 400ms):
- Пользователь набирает "Pink Floyd" (~10 символов) → ~8 событий onChange (после debounce ≈ 3-4 запроса)
- Каждый suggest = 2 запроса к Discogs (artists + masters, per_page=3+5)
- **Без кэша: 3-4 поиска × 2 = 6-8 токенов на один набор**
- **С кэшем: после первого ввода "Pink" → кэш, "Pink " → кэш miss, "Pink F" → кэш miss...**

**Вывод:** нужно ограничивать количество suggest-запросов, иначе 3 пользователя одновременно могут исчерпать bucket.

#### Решение: suggest через один endpoint с объединённым запросом

**Backend — НЕ два отдельных запроса, а один:**

```python
# НЕ делать:
# Parallel: search?type=artist + search?type=master  ← 2 токена!

# Делать:
# Один запрос: search?q=beatl&per_page=8  (без type= → ищет всё)
# И разделять результаты по type в ответе
```

Discogs API при поиске без `type=` возвращает микс: artists, masters, releases, labels. Каждый результат имеет поле `type`. Это **1 токен вместо 2**.

```python
# GET /records/suggest?q=beatl&limit=8

@router.get("/suggest")
async def suggest(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(8, ge=1, le=15),
):
    """
    Автодополнение: один запрос к Discogs, результаты разделяются по типу.
    """
    discogs = DiscogsService()
    # Используем общий поиск (без type=) — 1 запрос вместо 2
    results = await discogs.suggest(query=q, per_page=limit)
    return results
```

```python
# discogs.py — новый метод
async def suggest(self, query: str, per_page: int = 8) -> dict:
    params = {"q": query, "per_page": per_page}

    ck = search_cache_key({"suggest": True, **params})
    cached = await cache.get("suggest", ck)
    if cached is not None:
        return cached

    data = await self._get(
        f"{self.BASE_URL}/database/search",
        params=params,
        priority=Priority.SEARCH,
    )

    artists = []
    masters = []
    for item in data.get("results", []):
        item_type = item.get("type")
        if item_type == "artist":
            artists.append({
                "artist_id": str(item.get("id", "")),
                "name": item.get("title", ""),
                "thumb": item.get("thumb"),
            })
        elif item_type == "master":
            title = item.get("title", "")
            artist_name, album_title = ("Unknown", title)
            if " - " in title:
                parts = title.split(" - ", 1)
                artist_name, album_title = parts[0], parts[1]
            masters.append({
                "master_id": str(item.get("id", "")),
                "title": album_title,
                "artist": artist_name,
                "year": int(item["year"]) if item.get("year") else None,
                "thumb": item.get("thumb"),
            })

    result = {"artists": artists[:3], "masters": masters[:5]}
    await cache.set("suggest", ck, result, TTL_SEARCH)
    return result
```

#### Frontend

**Новое в store.ts** — отдельный легковесный стейт (НЕ в useSearchStore, чтобы не ломать существующий кэш):

```ts
interface SuggestState {
  suggestions: { artists: SuggestArtist[]; masters: SuggestMaster[] } | null;
  isLoading: boolean;
  query: string;
  fetchSuggestions: (q: string) => Promise<void>;
  clear: () => void;
}

export const useSuggestStore = create<SuggestState>((set, get) => ({
  suggestions: null,
  isLoading: false,
  query: '',

  fetchSuggestions: async (q) => {
    if (q.length < 2 || q.startsWith('@')) {
      set({ suggestions: null, query: q });
      return;
    }
    // Не дёргать API если запрос не изменился
    if (q === get().query && get().suggestions) return;

    set({ isLoading: true, query: q });
    try {
      const data = await api.suggest(q);
      // Только если запрос всё ещё актуален (не устарел за время запроса)
      if (q === get().query) {
        set({ suggestions: data, isLoading: false });
      }
    } catch {
      set({ isLoading: false });
    }
  },

  clear: () => set({ suggestions: null, query: '' }),
}));
```

**search.tsx:**

```tsx
// Debounce при наборе (400ms — достаточно для rate limit)
const suggestTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
const { suggestions, fetchSuggestions, clear: clearSuggestions } = useSuggestStore();

const handleSearchInputChange = useCallback((text: string) => {
  // ... существующая логика переключения @-режима ...
  setSearchInput(text);

  // Suggestions
  if (suggestTimer.current) clearTimeout(suggestTimer.current);
  if (text.length >= 2 && !text.startsWith('@')) {
    suggestTimer.current = setTimeout(() => fetchSuggestions(text), 400);
  } else {
    clearSuggestions();
  }
}, [/* deps */]);
```

Dropdown рендерится **между SearchHeader и результатами**, исчезает при `handleSearch()`:

```tsx
const handleSearch = useCallback(async () => {
  clearSuggestions();  // ← скрываем dropdown
  // ... существующая логика ...
}, [/* deps */]);
```

**Взаимодействие с существующим потоком:**
- `useSuggestStore` полностью изолирован от `useSearchStore` — разные сторы, разные ключи кэша
- `handleSearch()` по-прежнему вызывает `search()` из `useSearchStore` — основной поиск не меняется
- Suggestions скрываются при нажатии кнопки поиска или при выборе suggestion
- Нажатие на suggestion → `router.push()` без вызова `search()` → не засоряет кэш поиска

**Совместимость с `@`-режимом:** `fetchSuggestions` проверяет `q.startsWith('@')` и не вызывает API. Переключение в пользовательский режим очищает suggestions.

**Совместимость с фильтрами:** suggestions не используют фильтры (format/country/year). Это правильно — подсказки должны быть быстрыми и общими. Фильтры применяются только при полноценном поиске.

**Совместимость с rate limiter:**
- 1 suggest = 1 токен (не 2, т.к. общий search без type=)
- Debounce 400ms → максимум ~2.5 req/sec от одного пользователя
- Кэш на бэкенде (TTL 5 мин) → повторные "Pink" не дёргают Discogs
- При 10 одновременных пользователях: worst case 25 req/sec → bucket исчерпается за 2 сек. **Нужен серверный debounce / rate limit на suggest endpoint** (не более 2 req/sec на IP)

#### Серверный rate limit для suggest

```python
# Простое решение: если suggest-запрос приходит чаще 200ms от того же IP — вернуть 429
# Или: snapping — округлять query до 300ms окна и переиспользовать кэш

# Рекомендация: на первом этапе положиться на клиентский debounce 400ms
# + Redis кэш. Добавить серверный лимит только если мониторинг покажет проблему.
```

---

### Фаза 4 — Баннер "Показано по: X" (0.5 дня)

**Риск:** нулевой. Чисто фронтенд, без новых запросов.

**Логика (в store.ts, внутри `search()`):**

```ts
// После получения artistsResponse:
let correctedQuery: string | null = null;
const topName = artistsResponse.results[0]?.name;
if (topName) {
  const queryLower = query.toLowerCase().trim();
  const nameLower = topName.toLowerCase().trim();
  // Простая проверка: если запрос не является подстрокой имени артиста
  // и имя артиста не является подстрокой запроса → вероятно исправление
  if (
    !nameLower.includes(queryLower) &&
    !queryLower.includes(nameLower) &&
    queryLower !== nameLower
  ) {
    correctedQuery = topName;
  }
}
set({ correctedQuery });
```

**Почему без fuse.js / внешних библиотек:**
- Добавлять зависимость ради одного сравнения — overkill
- Простая проверка `includes` покрывает 90% кейсов: "Pnk Floyd" не включает "Pink Floyd" и наоборот → показываем баннер
- "Beatles" включается в "The Beatles" → НЕ показываем баннер (правильно, это не опечатка)

**Рендер:**
```tsx
{correctedQuery && (
  <View style={styles.correctionBanner}>
    <Text>Показаны результаты для: <Text style={{ fontWeight: 'bold' }}>{correctedQuery}</Text></Text>
    <TouchableOpacity onPress={() => { /* искать точно оригинальный запрос */ }}>
      <Text style={styles.correctionLink}>Искать "{query}"</Text>
    </TouchableOpacity>
  </View>
)}
```

**Добавить в SearchState:**
```ts
correctedQuery: string | null;
// в clearResults:
correctedQuery: null,
```

**Совместимость с кэшем:** `correctedQuery` — transient state, не сохраняется в `useCacheStore.setSearch()`. При повторном заходе из кэша — не показывается. Это ок: баннер нужен только при первом поиске с опечаткой.

Но если хочется сохранять — добавить в `SearchCacheEntry`:
```ts
interface SearchCacheEntry {
  results: ...;
  artistResults: ...;
  // добавить:
  correctedQuery: string | null;
}
```
Это безопасно: старые записи кэша без этого поля просто вернут `undefined` → `|| null`.

---

### Фаза 5 — Транслитерация кириллицы (1 день)

**Риск: НИЗКИЙ, но нужна осторожность с rate limit.**

**Где реализовать:** на бэкенде, в `DiscogsService.search()` / `search_masters()` / `search_artists()`.

**Логика:**
```python
import re

_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')

TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo',
    'ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m',
    'н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u',
    'ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'sch',
    'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}

def transliterate(text: str) -> str | None:
    """Транслитерирует кириллицу → латиницу. None если нет кириллицы."""
    if not _CYRILLIC_RE.search(text):
        return None
    return ''.join(TRANSLIT.get(c, TRANSLIT.get(c.lower(), c).upper() if c.isupper() else TRANSLIT.get(c, c)) for c in text)
```

**КРИТИЧНО: НЕ делать 2 параллельных запроса.**

Старая версия плана предлагала "два параллельных запроса: оригинал + транслитерация". Это **удвоит** расход токенов rate limiter'а. Правильный подход:

```python
async def search_artists(self, query, ...):
    translit = transliterate(query)
    # Если есть кириллица — искать ТОЛЬКО по транслитерации
    # Discogs не знает кириллицу, оригинальный запрос даст 0 результатов
    effective_query = translit if translit else query

    params = {"q": effective_query, "type": "artist", ...}
    # ... далее существующая логика ...
```

**Почему не два запроса:** Discogs — англоязычная база. Запрос "Битлз" вернёт 0 результатов. Нет смысла тратить токен на заведомо пустой ответ. Транслитерация "Bitlz" хотя бы имеет шанс на fuzzy match → "Beatles".

**Совместимость с кэшем:** ключ кэша строится из `params`, куда попадёт `effective_query`. Запрос "Битлз" и запрос "Bitlz" будут разными ключами — это правильно. Прямой запрос "Bitlz" (латиницей) тоже закэшируется отдельно.

**Где именно вставить транслитерацию:**

| Метод | Нужна? | Почему |
|---|---|---|
| `search()` (releases) | Да | Пользователь может искать "Битлз Эбби Роуд" |
| `search_masters()` | Да | Аналогично |
| `search_artists()` | Да | Основной кейс |
| `search_releases()` | Да | То же |
| `suggest()` (новый) | Да | Подсказки тоже должны работать |
| `search_by_barcode()` | Нет | Баркод — цифры |
| `get_release()` / `get_artist()` | Нет | Принимают ID, не текст |

**Лучше сделать один раз в `_get` или в отдельном хелпере**, который вызывается перед формированием `params["q"]`.

---

### Фаза 6 (опционально) — Умная маршрутизация (2–3 дня)

**Риск: СРЕДНИЙ** — эвристики могут давать ложные срабатывания.

**Решение из предыдущей версии плана пересмотрено:**

Ранее предлагалось: `detectSearchIntent()` на фронте меняет тип запроса. Проблема: если эвристика ошибётся (решит что "Radiohead" — это альбом), пользователь не увидит артиста.

**Новое предложение (безопаснее):** не менять запросы, а менять **порядок отображения**:

```ts
// search.tsx — визуальный приоритет, не логика запросов
const artistsFirst = artistResults.length > 0 &&
  artistResults[0].name.toLowerCase().includes(query.toLowerCase());
```

Если топ-артист содержит запрос → секция артистов рендерится ДО релизов.
Если нет → текущий порядок (артист сверху, релизы ниже — уже так).

Это минимальное изменение, которое не ломает запросы и не рискует скрыть результаты.

**Рекомендация:** отложить на после фаз 1-5, реализовать только если UX-тестирование покажет проблему.

---

## Итоговый план с оценкой рисков

| # | Задача | Файлы | Новые запросы к Discogs | Риск поломки | Приоритет |
|---|---|---|---|---|---|
| **1** | Показать нескольких артистов | search.tsx | 0 | Нулевой | **Сейчас** |
| **2** | Поднять per_page артистов 10→15 | store.ts | 0 (тот же запрос, больше данных) | Нулевой | **Сейчас** |
| **3** | Баннер "Показано по: X" | store.ts + search.tsx | 0 | Нулевой | **Сейчас** |
| **4** | Транслитерация кириллицы | discogs.py + новый utils | 0 (замена query, не доп. запрос) | Низкий | **Следующий** |
| **5** | Автодополнение (suggest) | discogs.py + records.py + store.ts + search.tsx | +1 за каждый debounced ввод | Средний (rate limit) | **После 4** |
| **6** | Умная маршрутизация | search.tsx | 0 | Низкий | Опционально |

### Зависимости между фазами

```
Фаза 1 ─┐
Фаза 2 ─┼── независимы, можно делать параллельно
Фаза 3 ─┘
Фаза 4 ──── независима
Фаза 5 ──── зависит от 4 (suggest должен тоже транслитерировать)
Фаза 6 ──── зависит от 1 (нужна секция с несколькими артистами)
```

### Чеклист "не сломай"

- [ ] `useCacheStore` — формат `SearchCacheEntry` расширяется обратно-совместимо (добавление `correctedQuery`)
- [ ] Rate limiter — suggest-endpoint расходует 1 токен (не 2), debounce ≥ 400ms
- [ ] `@`-режим — suggest не вызывается для запросов начинающихся с `@`
- [ ] `clearResults()` — должен очищать и новые поля (`correctedQuery`, suggestions)
- [ ] `handleSearch()` — при нажатии кнопки поиска suggestions скрываются
- [ ] Кэш Redis — suggest использует отдельный namespace (`"suggest"`, не `"search_artist"`)
- [ ] Транслитерация — применяется ДО формирования cache key, чтобы "Битлз" и "Bitlz" были разными записями
- [ ] Circuit breaker — suggest-запросы проходят через тот же breaker (не обходят его)
