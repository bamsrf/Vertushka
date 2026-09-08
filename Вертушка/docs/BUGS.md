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

**Статус:** ✅ закрыт 2026-09-08, PR `fix/android-bugs-a1-a6` — `SOCIAL_PROVIDERS_LABEL` в `register.tsx`, на iOS текст прежний буква в букву.

---

### A2. [android] Иконки статус-бара светлые на светлом фоне во время splash и интро
**Файлы:** `Mobile/app.json` (splash `backgroundColor: #FAFBFF`), `Mobile/app/_layout.tsx:495`

Первые ~6 с холодного старта (нативный splash + `MascotIntro`) часы/сеть/батарея рисуются белым на #FAFBFF — не читаются. `<StatusBar style="dark" />` из JS применяется, но визуально стиль появляется только к моменту логина. В сгенерированном `android/app/src/main/res/values/styles.xml` нет `windowLightStatusBar`, т.е. нативно тема статус-бара не задана и до маунта JS действует системный дефолт.

**Фикс:** задать стиль нативно — `"androidStatusBar": {"barStyle": "dark-content"}` в `app.json` (prebuild пропишет `windowLightStatusBar=true` в тему), перепроверить после `prebuild --clean`. P3, простая.

**Статус:** ✅ закрыт 2026-09-08, PR `fix/android-bugs-a1-a6` — `androidStatusBar: {barStyle: dark-content, backgroundColor: #FAFBFF}` (ключи по `@expo/config-types` SDK 57; `translucent` не задан — под edge-to-edge не нужен). iOS-секции `expo config --type introspect` не касается, `ci/check-ios-baseline.sh` зелёный без обновления baseline. Перепроверить визуально после `prebuild --clean` на эмуляторе.

---

### A3. [android] ExpoVideo спамит E-логом про picture-in-picture
**Файлы:** `Mobile/components/MascotIntro.tsx:164–170`, `Mobile/app.json` (plugin `expo-video`)

На каждый маунт `VideoView` в logcat трижды падает `E ExpoVideo: Current activity does not support picture-in-picture. Make sure you have configured the expo-video config plugin correctly`, хотя `allowsPictureInPicture={false}`. Функционально не мешает, но уровень E попадает в breadcrumbs Sentry и мешает искать реальные ошибки.

**Фикс:** проверить в `expo-video` (SDK 57), проходит ли проверка PiP независимо от пропа; если да — либо включить `["expo-video", {"supportsPictureInPicture": true}]` (снимет лог ценой флага на Activity), либо завести issue. P3.

**Статус:** ⏸ won't fix / upstream (2026-09-08). Проверено по коду `expo-video@57.0.x`: лог пишет `runWithPiPMisconfigurationSoftHandling` (`android/src/main/java/expo/modules/video/utils/PictureInPictureUtils.kt:68–72`) — `Log.e` на `IllegalStateException` из `Activity.setPictureInPictureParams`. Туда ведёт `PictureInPictureManager.findAndSetupPipCandidate()` (`managers/PictureInPictureManager.kt:68–84`), который зовётся при регистрации КАЖДОГО `VideoView` и вызывает `applyPiPParams(activity, autoEnterPiP)` безусловно — проп `allowsPictureInPicture={false}` на это не влияет, он лишь выключает auto-enter. Единственный способ убрать лог — `android:supportsPictureInPicture="true"` на MainActivity через `["expo-video", {"supportsPictureInPicture": true}]` (`plugin/build/withExpoVideo.js:24–27`), т.е. лишний флаг Activity ради одного немого интро — не включаем. Уровень E безвреден (исключение проглочено).

---

### A4. [android] Console error expo-router при холодном старте dev-client
**Стек:** `useLinking.native.js:127` (`url.then$argument_0` → `dispatchSetState`) под `<ExpoRoot>`

LogBox: «Can't perform a React state update on a component that hasn't mounted yet». Код приложения в стеке отсутствует — это `Linking.getInitialURL().then(setState)` внутри expo-router, срабатывающий до маунта при запуске через `exp+vertushka://expo-development-client/?url=…`. Воспроизведено на каждом холодном старте dev-client.

**Фикс:** на стороне приложения нет. Проверить на release-APK (там нет dev-launcher deep link); если воспроизводится — issue в expo-router (SDK 57 / React 19). P3.

**Статус:** ⏸ upstream / dev-client-only (2026-09-08). Код не трогаем. **Проверить на release APK** (`eas build -p android --profile production` или `expo run:android --variant release`); если воспроизводится без dev-launcher — issue в expo-router.

---

### A5. [android] MascotIntro: при медленной отдаче mp4 — 6.7 с пустого экрана
**Файл:** `Mobile/components/MascotIntro.tsx:96–160`

Наблюдение, не дефект сборки: при первом запуске (ассет `intro-mascot.mp4`, 2 МБ, ехал по сети из Metro) плеер не успел дойти до `readyToPlay`, `ready` остался `false`, экран был пустым белым до safety-timeout — в логе `[MascotIntro] интро не доиграло за 6710мс`. Повторные запуски играли штатно (ExoPlayer h264 ≈ 6 с). В release ассет внутри APK, но на бюджетниках с медленным флешем/декодером риск тот же.

**Фикс (опционально):** под `VideoView` показывать статичный первый кадр (png) до `readyToPlay`, чтобы таймаут не выглядел как зависание. P3.

**Статус:** ✅ закрыт 2026-09-08, PR `fix/android-bugs-a1-a6` — `assets/video/intro-mascot-first-frame.png` (960×960, первый кадр mp4 через ffmpeg, фон #FAFBFF как у ролика) рендерится в `MascotIntro` вместо `VideoView` строго пока `!ready`; в момент `readyToPlay` подменяется плеером, картинка и кадр совпадают попиксельно — мигания нет, iOS-поведение не меняется. Команда перевытаскивания кадра — в комментарии к `INTRO_FIRST_FRAME`.

---

### A6. [android] Иконка замка в полях пароля рисуется как «+»
**Файлы:** `Mobile/components/ui/Icon.tsx:228,353` (карта), `Mobile/app/(auth)/login.tsx:134`, `register.tsx:134,144`, `reset-password.tsx:110`, `app/user/[username]/index.tsx:955`

`leftIcon="lock-closed-outline"` передаётся в `<Icon>`, но в registry есть только `lock-open` / `lock-open-outline`; неизвестное имя уходит в фолбэк `'plus'` (Icon.tsx:145). На экране логина слева от поля «Пароль» — плюс вместо замка. Не Android-специфично — тот же путь на iOS, просто замечено на эмуляторе.

**Фикс:** добавить в карту `'lock-closed'`/`'lock-closed-outline'` → `LockIcon` (phosphor `Lock`); в `user/[username]` — та же строка. P2, простая.

**Статус:** ✅ закрыт 2026-09-08, PR `fix/android-bugs-a1-a6` — `'lock-closed'` → `LockIcon` в registry, `'lock-closed-outline'` в alias-таблице, `LockIcon` добавлен в ambient-шим `types/phosphor-react-native.d.ts`. Покрывает login/register/reset-password и `user/[username]` (все шли через `<Icon>`, правок в экранах не нужно). Общий баг — чинится и для iOS.

---

## 🤖 Android-порт — QA-прогон WS7 на эмуляторе (2026-09-08, за логином)

Прогон dev-client (`expo run:android`, Metro :8087) на `pixel8_api36` (Android 16, arm64) под тестовым аккаунтом `@test1` на прод-бэкенде. Пройдены сценарии 1–15 из задания WS7 (жестовая и 3-кнопочная навигация, тёмная тема, font_scale 1.3). Скриншоты — `NN-name.small.png` в scratchpad сессии. Тег `[android]`. Прогон остановлен до записи в этот файл, записи ниже собраны из транскрипта.

### A7. [android] `AnimatedGradientText`: worklet падает с «Cannot convert undefined value to object»
**Файл:** `Mobile/components/AnimatedGradientText.tsx:67` (`useAnimatedProps` → `interpolateColor(t, [0,1], [presets[fromIdx][0], presets[toIdx][0]])`); использования — `app/(tabs)/collection.tsx` (заголовок «Коллекция»), `app/profile.tsx:384`, `app/notifications.tsx:404`

**Шаги:** холодный старт → главная (Коллекция) → хардверный Back (→ Поиск) → снова Коллекция. LogBox: `Uncaught Error: Cannot convert undefined value to object`, source — строка 67. За сессию 2 раза (`ERROR [TypeError: Cannot convert undefined value to object]` ×2 в Metro-логе), 4 переключения табов подряд повторно не воспроизвели.

**Ожидаемое:** градиентный заголовок анимируется без ошибок. **Фактическое:** uncaught-исключение в worklet на UI-потоке; в dev — красный LogBox поверх экрана, в release такое исключение в Reanimated-worklet может уронить процесс.

**Гипотеза:** `presets[fromIdx]` оказывается `undefined` — индекс вне диапазона, когда `progress.value` на момент вычисления не число (NaN после `cancelAnimation`/`freezeOnBlur` при уходе с таба — `Math.floor(NaN) % PRESET_COUNT` = NaN). Нужен guard: `Number.isFinite(raw)` + клемп индексов, либо не отменять анимацию, а ставить `progress.value = 0` при потере фокуса. Проверить, воспроизводится ли на iOS (код общий). Скриншоты: `09-3btn-now`, `04-after-2-backs`. **P1.**

---

### A8. [android] Таб-бар: пилюля скруглена только справа — левый верхний угол квадратный
**Файл:** `Mobile/components/GlassTabBar.tsx:181–194` (контейнер: `elevation: 0` + тень через `androidShadow`/`boxShadow`; внутренний `BlurViewCompat`/`AndroidGlass`: `borderRadius: 36, overflow: 'hidden'`), `Mobile/constants/theme.ts:505` (`androidShadow`)

**Шаги:** любой таб, посмотреть на пилюлю таб-бара (зум на углы).

**Ожидаемое:** все четыре угла со скруглением 36. **Фактическое:** заливка пилюли скруглена по правому и нижнему краям, левый верхний угол прямой (на кропе `05-tab-tl.png` — прямой угол заливки, `05-tab-br.png` — правильный радиус). Похоже на конфликт `boxShadow` родителя без фона с `overflow: hidden` у дочернего скруглённого view на Fabric. Проверить: дать `borderRadius: 36` самому контейнеру с тенью, либо перенести `boxShadow` на тот же view, что и радиус. Скриншоты: `05-search-tab`, кропы `05-tab-tl.png`, `05-tab-br.png`. **P2.**

---

### A9. [android] `PromptSheet` (создать/переименовать папку): клавиатура не поднимается по тапу в поле
**Файл:** `Mobile/components/ui/PromptSheet.tsx` (RN `Modal` + `TextInput autoFocus` + `onShow={() => inputRef.current?.focus()}`)

**Шаги:** Коллекция → «Создать папку» → шит открылся, поле помечено `focused=true` → тап в поле (дважды).

**Ожидаемое:** IME показывается, поле над клавиатурой. **Фактическое:** `dumpsys input_method`: `mInputShown=false`, `mServedView=DecorView[MainActivity]` — IME обслуживает окно Activity, а не окно `Modal`; после двух тапов в создании папки IME так и не показан (`57-prompt-kbd-up`, `56-prompt-reopen`). Ввод через `adb input text` (аппаратный путь) проходит, папка создаётся (`58-folder-created`). В переименовании (`63-rename-tap2`) после тапа IME стал `visible=true`, но с нулевой высотой — эмулятор был в режиме hardware-keyboard с Gboard, свёрнутым в мини-тулбар, поэтому воспроизведение не чистое.

**Статус:** ⚠️ воспроизведено 2 из 3 попыток, нужна перепроверка на реальном устройстве без аппаратной клавиатуры. Если подтвердится — сравнить с `OptionsSheet`/`ThresholdSheet` и попробовать `focus()` с задержкой после `onShow` либо `Keyboard`-вызов через `InteractionManager`. Скриншоты: `54-prompt-sheet`, `57-prompt-kbd-up`, `63-rename-tap2`. **P1 (если подтвердится).**

---

### A10. [android] Ачивки: хардверный Back на `DetailsSheet` закрывает весь экран, а не шит
**Файл:** `Mobile/app/achievements.tsx` — `DetailsSheet` (inline `<View style={styles.sheetBackdrop}>`, не `Modal`, без `useAndroidBackClose`/`BackHandler`)

**Шаги:** Ачивки → тап по открытой ачивке («Хотелка») → шит с деталями → хардверный Back.

**Ожидаемое:** закрывается только шит, экран ачивок остаётся. **Фактическое:** Back выполняет `router.back()` — уходим на Коллекцию (`94-after-back`), шит и экран пропали вместе. Нарушает сценарий 15 («Назад» закрывает шит, а не уводит с экрана). Фикс: `useAndroidBackClose(!!selected, close)` (как у других шитов) или обернуть в `Modal` с `onRequestClose`. Скриншоты: `91-achievement-detail`, `94-after-back`. **P2.**

---

### A11. [android] Ачивки: после закрытия share-chooser кнопка «Поделиться» залипает в «Готовим…»
**Файл:** `Mobile/app/achievements.tsx` — ветка share в `DetailsSheet` (флаг загрузки не сбрасывается после `Share.share`/`Sharing.shareAsync`, если chooser закрыт без выбора)

**Шаги:** шит ачивки → «Поделиться» → системный chooser открылся с картинкой (view-shot отработал ✅, `92-achievement-share`) → Back.

**Ожидаемое:** кнопка возвращается в «Поделиться». **Фактическое:** кнопка остаётся «Готовим…» и задизейблена (`93-after-share`); повторный share без переоткрытия шита невозможен. Вероятно, `setSharing(false)` стоит только в success-ветке, а на Android отмена chooser'а резолвится как `dismissedAction`/без ошибки. Фикс — `finally`. Не Android-специфично по коду, проверить iOS. **P3.**

---

### A12. [android] Профиль: «Оценить в App Store» и Apple-URL на Android
**Файлы:** `Mobile/app/profile.tsx:119` (`APP_STORE_FALLBACK_URL = 'https://apps.apple.com/ru/app/…'`), `handleRateApp` (добавляет `?action=write-review` — iOS-only параметр), подпись пункта меню «Оценить в App Store»; `Mobile/lib/remoteConfig.ts:38` (per-platform `store_url` уже поддержан)

**Шаги:** Профиль → скролл вниз → блок ссылок.

**Ожидаемое:** на Android — «Оценить в Google Play» и ссылка `market://details?id=com.vertushka.app` (или `https://play.google.com/store/apps/details?id=…`) из `platforms.android.store_url`. **Фактическое:** подпись «App Store», фолбэк ведёт в apps.apple.com, к любому URL дописывается `?action=write-review`. Пока Play-листинга нет — хотя бы платформенная подпись и фолбэк-заглушка; после WS8 — реальный URL в `/api/config/`. Скриншот: `72-profile-bottom`. **P2.**

---

### A13. [android] Сообщения: список навсегда в skeleton, пустое состояние не показывается
**Файлы:** `Mobile/app/messages/index.tsx` (условие skeleton по `isLoadingList`, эффект загрузки ~528–548), `Mobile/lib/messagesStore.ts` (`loadConversations`, два присваивания `isLoadingList`), `Mobile/lib/messagesApi.ts` (свой axios-клиент с интерцептором `SecureStore.getItemAsync(TOKEN_KEY)`)

**Шаги:** deep link `vertushka://messages` (аккаунт без диалогов) → разрешить уведомления → ждать 10 с, 40 с → pull-to-refresh → перемонтировать экран → таб «Запросы».

**Ожидаемое:** пустое состояние «нет сообщений» через секунду-две. **Фактическое:** обе вкладки бесконечно показывают skeleton (`97-messages-list`, `100-messages-refresh`, `101-messages-remount`, `99-requests`); в Metro нет `loadConversations failed`, в logcat нет сетевых ошибок; параллельно `/notifications` и остальные API отвечают нормально, `devApiUrl` в `messagesApi.ts` тот же, что в `api.ts`. Причина не найдена в рамках прогона — подозрение на зависание `getClient()`/интерцептора или на skeleton-условие для пустого ответа `[]`. Блокирует сценарий 7 (меню чата, клавиатура чата не проверены). Проверить на iOS с пустым аккаунтом — вероятно, не Android-специфично. **P1.**

**Статус:** ✅ закрыт 2026-09-08, PR #174 — корень в клиенте: `loadConversations('primary')`/`('requests')` летят параллельно с одним `isLoadingList` (первый ответ гасил флаг, пока второй в полёте), skeleton монтировался на каждый refresh, а `exiting={FadeOut}` на `InboxSkeleton` в `ListEmptyComponent` на Android (Fabric) оставлял «призрак» поверх пустого состояния. Теперь счётчик in-flight запросов + `listLoadedOnce` (skeleton только до первого ответа, `[]` = пустое состояние), exiting снят. Бэкенд для юзера без диалогов честно отдаёт `[]`/200. Jest: `__tests__/messagesStore.test.ts`. Эмулятор не проверялся — подтвердить на следующем QA-прогоне.

---

### A14. [android] Уведомления/профиль: «3 ч» для ачивки, открытой минуту назад — naive UTC без офсета
**Файлы:** `Backend/app/models/notification.py:76,91` (`default=datetime.utcnow`, naive) → `Backend/app/schemas/notification.py:31,97` (`created_at: datetime` сериализуется без `Z`); `Mobile/components/notifications/NotificationItem.tsx:48` (`new Date(iso)`), то же в `ActivityCard.tsx:16`, `SocialFeedRow.tsx:24`

**Шаги:** получить ачивку → Профиль → блок «Уведомления» / экран Уведомлений.

**Ожидаемое:** «1 мин». **Фактическое:** «3 ч» / «4 ч» (`102-notifications`, `70-profile`) — эмулятор в Europe/Moscow (UTC+3), строка без офсета парсится как локальное время. Не Android-специфично (Hermes на обеих платформах трактует ISO без зоны как local). Фикс на бэке: `datetime.now(timezone.utc)` + сериализация с офсетом (или `model_serializer` → `isoformat()` с `Z`); на клиенте — парсить naive как UTC. **P2.**

**Статус:** ✅ закрыт 2026-09-08, PR #174 — `Backend/app/schemas/utc.py`: `UtcDatetime` (naive → UTC при сериализации, в JSON `Z`) на всех datetime-полях `schemas/message.py` и `schemas/notification.py`, `utc_isoformat()` в WS-событиях `message.read`/`message.edited` и ответе `mute-duration`; хранение (naive колонки, сравнения с `utcnow()`) не тронуто. Клиент: `Mobile/lib/serverDate.ts::parseServerDate` трактует naive ISO как UTC в `NotificationItem`/`ActivityCard`/`SocialFeedRow`/инбокс/presence/пузырь. Тесты: `Backend/tests/test_utc_datetime_serialization.py`, `Mobile/__tests__/serverDate.test.ts`.

---

### A15. [android] expo-notifications: `ERROR Custom sound 'default' not found in native app` на каждый старт
**Файл:** `Mobile/lib/push.ts` — `setNotificationChannelAsync(…, { sound: 'default', … })`

**Шаги:** любой холодный старт / открытие Сообщений (4 раза за сессию).

**Ожидаемое:** канал создаётся молча. **Фактическое:** ERROR-лог + LogBox-тост, перекрывающий низ экрана в dev (`122-deeplink-record`, `124-deeplink-record`). Канал при этом создан корректно — `dumpsys notification`: `mSound=content://settings/system/notification_sound`, importance 5, т.е. функционально звук есть. В SDK 57 для дефолтного звука `sound` надо не передавать (или передать `undefined`), строка `'default'` трактуется как имя raw-ресурса. **P3** (шум в логах/Sentry; в release не видно).

---

**Статус:** ✅ закрыт 2026-09-08, #172 (`sound` убран из `setNotificationChannelAsync`).


### A16. [android] Ачивки: спиннер загрузки системного бирюзового цвета
**Файлы:** `Mobile/app/achievements.tsx:171` (`<ActivityIndicator size="large" />`), `Mobile/components/AchievementsBlock.tsx:82` (`<ActivityIndicator />`) — без `color`

**Шаги:** открыть Ачивки на медленной сети.

**Ожидаемое:** индикатор в цвете бренда (`Colors.primary`), как в `messages/new.tsx`, `share-record.tsx`, `ui/Button.tsx`. **Фактическое:** Android-дефолт `colorAccent` (teal) — `88-achievements`. На iOS дефолт серый, поэтому не бросалось в глаза. **P3.**

---

### A17. [android] Коллекция: пустое состояние при первом рендере лежит под таб-баром
**Файл:** `Mobile/app/(tabs)/collection.tsx` — `contentContainerStyle.paddingBottom` списка / отступ пустого состояния относительно высоты `GlassTabBar` + nav bar inset

**Шаги:** пустая коллекция, открыть таб без скролла.

**Ожидаемое:** «Здесь будут твои пластинки» и кнопки видны целиком над таб-баром. **Фактическое:** заголовок и подпись перекрыты пилюлей таб-бара (`01-home`, `13-collection-3btn-c`); после скролла всё доступно (`03-home-scrolled`, `94-after-back`) — контент не обрезан, только начальная позиция. Добавить нижний отступ = высота таб-бара + `insets.bottom`. **P3.**

---

### Наблюдения dev-client (не баги)

- **Metro-варнинги, повторяющиеся на каждый ребут бандла** (10 бутов за сессию): `Require cycle: lib/store.ts -> lib/messagesStore.ts -> lib/store.ts`; `Require cycle: lib/store.ts -> lib/achievementsBus.ts -> components/AchievementUnlockOverlay.tsx -> lib/reviewPrompt.ts -> lib/store.ts`; `Require cycle: components/ui/index.ts -> components/ui/Input.tsx -> components/ui/index.ts`; `… -> components/ui/ActionSheet.tsx -> components/ui/index.ts`; `setLayoutAnimationEnabledExperimental is currently a no-op in the New Architecture` (×2 на бут); `[Analytics] AMPLITUDE_API_KEY_DEV не задан в Mobile/.env — аналитика отключена`. Разово: `Some of the used filters are not yet supported on native platforms` (SVG-фильтры), `[MascotIntro] интро не доиграло за 6710мс` (см. A5).
- **3-кнопочная навигация:** кнопки nav bar не попадают в `screencap` на Android 16 (Taskbar рисуется отдельной surface) — на скриншотах `13-collection-3btn-c`, `07/08-*-3btn` полоса пустая. Через `emu screenrecord screenshot` кнопки видны, приложение рисует `LIGHT_NAVIGATION_BARS` корректно, таб-бар и sticky-кнопки карточки лежат над панелью (`29-wishlist-added`, `32-record-wishlisted`). Не баг приложения.
- **Индикатор активного таба** на `06-scan-tab` показан под Поиском при активном Скане — скриншот снят в момент анимации; на поздних снимках (`128-dark-home`, `135-fs10-scan`) индикатор под Сканом. Считать лагом захвата, при живом прогоне на устройстве глянуть ещё раз.
- **Back на корне:** Back с Коллекции ведёт на Поиск (порядок табов search → scan → collection, дефолтный `backBehavior: firstRoute`), второй Back на Поиске оставил `MainActivity` в фокусе (`04-after-2-backs`) — возможно, Back съел LogBox-тост. Поведение iOS-нейтрально; если нужен «Back с любого таба = выход», задать `backBehavior: 'none'`.
- **Gboard на эмуляторе** при включённом hardware-keyboard сворачивается в мини-тулбар (`52-step3-kbd-typed`, `41-gboard-menu`), `adb input text` дополнительно его схлопывает — поэтому проверки клавиатуры делались с `show_ime_with_hard_keyboard=1` и `pm clear` Gboard (после которого всплыл его first-run диалог «Try out your stylus», `61/65-rename-*`). Ручное добавление шаг 2/3 и Редактирование профиля: поля над клавиатурой, футер прячется по `keyboardDidShow` и возвращается ✅ (`42-manual-kbd-full`, `77-edit-kbd`).
- **Кроп обложки** при ручном добавлении — стоковый `ExpoCropImageActivity` (`36-manual-cover`): функционально ок, без темы приложения; общий для expo-image-picker.
- **Deep link из холодного старта** через dev-client: `am start -d vertushka://record/…` после `force-stop` попадает в dev-launcher (ожидаемо), вариант с path в `expo-development-client` URL ломает загрузку манифеста (`120-after-reload`). По факту `view_record 1799731` отработал сразу после холодного бута JS (`124-deeplink-record`), тёплый deep link ✅ (`125-warm-deeplink`). Окончательно — на release-APK.
- **font_scale 1.3** перезапускает Activity (штатно для Android без `configChanges=fontScale`); «Наведите камеру на штрихкод пластинки» переносится на две строки (`134-fs13-collection`). Рост текста: `Штрихкод` 196→228 px (+16%), `Обложка` 170→197 (+16%), `Сканирование` 408→466 (+14%) — в пределах `MAX_FONT_SCALE = 1.15`. Один раз после смены масштаба процесс ушёл с переднего плана (`136-relaunched`), crash/kill в logcat не найден — не подтверждено.
- **Тёмная тема:** `userInterfaceStyle: light` — приложение остаётся светлым при `cmd uimode night yes` (`127-dark-record`, `130-dark-collection`), иконки статус-бара тёмные ✅.
- **Маркет:** карточки магазина Plastinka.com без обложек — плейсхолдеры (`112-store`), это данные каталога, не рендер.
