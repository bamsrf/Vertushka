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

---

## 🤖 Android-порт — найдено на эмуляторе (WS4, 2026-09-08)

Прогон debug-сборки (`expo run:android`, dev-client) на `pixel8_api36` (Android 16, arm64). Без учётки пройдены: splash → MascotIntro → логин, регистрация, «Забыли пароль», legal-страницы, валидация пустых форм, хардверный Back. Экраны за логином не проверены — пароль демо-аккаунта не хранится в репо. Тег `[android]`.

### A1. [android] Подпись под соц-кнопками регистрации обещает Apple Sign In
**Файл:** `Mobile/app/(auth)/register.tsx:185`

Текст «Вход через Apple или Discogs — тоже согласие с ними» показывается и на Android, где Apple-кнопки нет (`SocialAuthButtons.tsx:172`: `showApple = Platform.OS === 'ios' && …`). Пользователь видит обещание входа, которого нет — ровно то, чего комментарий над строкой хотел избежать для Google.

**Фикс:** собирать подпись из фактически показанных провайдеров (`Platform.OS === 'ios' ? 'Apple или Discogs' : 'Discogs'`), либо вынести строку в `SocialAuthButtons`, где список провайдеров уже известен. P2, простая.

---

### A2. [android] Иконки статус-бара светлые на светлом фоне во время splash и интро
**Файлы:** `Mobile/app.json` (splash `backgroundColor: #FAFBFF`), `Mobile/app/_layout.tsx:495`

Первые ~6 с холодного старта (нативный splash + `MascotIntro`) часы/сеть/батарея рисуются белым на #FAFBFF — не читаются. `<StatusBar style="dark" />` из JS применяется, но визуально стиль появляется только к моменту логина. В сгенерированном `android/app/src/main/res/values/styles.xml` нет `windowLightStatusBar`, т.е. нативно тема статус-бара не задана и до маунта JS действует системный дефолт.

**Фикс:** задать стиль нативно — `"androidStatusBar": {"barStyle": "dark-content"}` в `app.json` (prebuild пропишет `windowLightStatusBar=true` в тему), перепроверить после `prebuild --clean`. P3, простая.

---

### A3. [android] ExpoVideo спамит E-логом про picture-in-picture
**Файлы:** `Mobile/components/MascotIntro.tsx:164–170`, `Mobile/app.json` (plugin `expo-video`)

На каждый маунт `VideoView` в logcat трижды падает `E ExpoVideo: Current activity does not support picture-in-picture. Make sure you have configured the expo-video config plugin correctly`, хотя `allowsPictureInPicture={false}`. Функционально не мешает, но уровень E попадает в breadcrumbs Sentry и мешает искать реальные ошибки.

**Фикс:** проверить в `expo-video` (SDK 57), проходит ли проверка PiP независимо от пропа; если да — либо включить `["expo-video", {"supportsPictureInPicture": true}]` (снимет лог ценой флага на Activity), либо завести issue. P3.

---

### A4. [android] Console error expo-router при холодном старте dev-client
**Стек:** `useLinking.native.js:127` (`url.then$argument_0` → `dispatchSetState`) под `<ExpoRoot>`

LogBox: «Can't perform a React state update on a component that hasn't mounted yet». Код приложения в стеке отсутствует — это `Linking.getInitialURL().then(setState)` внутри expo-router, срабатывающий до маунта при запуске через `exp+vertushka://expo-development-client/?url=…`. Воспроизведено на каждом холодном старте dev-client.

**Фикс:** на стороне приложения нет. Проверить на release-APK (там нет dev-launcher deep link); если воспроизводится — issue в expo-router (SDK 57 / React 19). P3.

---

### A5. [android] MascotIntro: при медленной отдаче mp4 — 6.7 с пустого экрана
**Файл:** `Mobile/components/MascotIntro.tsx:96–160`

Наблюдение, не дефект сборки: при первом запуске (ассет `intro-mascot.mp4`, 2 МБ, ехал по сети из Metro) плеер не успел дойти до `readyToPlay`, `ready` остался `false`, экран был пустым белым до safety-timeout — в логе `[MascotIntro] интро не доиграло за 6710мс`. Повторные запуски играли штатно (ExoPlayer h264 ≈ 6 с). В release ассет внутри APK, но на бюджетниках с медленным флешем/декодером риск тот же.

**Фикс (опционально):** под `VideoView` показывать статичный первый кадр (png) до `readyToPlay`, чтобы таймаут не выглядел как зависание. P3.

---

### A6. [android] Иконка замка в полях пароля рисуется как «+»
**Файлы:** `Mobile/components/ui/Icon.tsx:228,353` (карта), `Mobile/app/(auth)/login.tsx:134`, `register.tsx:134,144`, `reset-password.tsx:110`, `app/user/[username]/index.tsx:955`

`leftIcon="lock-closed-outline"` передаётся в `<Icon>`, но в registry есть только `lock-open` / `lock-open-outline`; неизвестное имя уходит в фолбэк `'plus'` (Icon.tsx:145). На экране логина слева от поля «Пароль» — плюс вместо замка. Не Android-специфично — тот же путь на iOS, просто замечено на эмуляторе.

**Фикс:** добавить в карту `'lock-closed'`/`'lock-closed-outline'` → `LockIcon` (phosphor `Lock`); в `user/[username]` — та же строка. P2, простая.
