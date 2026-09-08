# Android-порт Вертушки — план работ

> **Родитель:** [ROADMAP.md](../../../ROADMAP.md) → M2 (Production Release: App Store + Google Play)
> **Составлен:** 2026-09-07 · **Редакция 2** после adversarial review (3 ревьюера: изоляция iOS, процесс Play/Firebase/EAS по актуальным докам, техническая реализуемость по коду) · **Статус:** 🟢 в работе. Синк 07.09: аккаунты/доступы (WS1, Q1, Q9, Q13) отложены, сначала готовим приложение; приоритет — дыры в изоляции iOS. WS0 + WS0b ✅ (#159), WS2 ✅ (#161), WS3 ✅ (#160), WS5a ✅ (#162), WS5b ✅ (#163 + #166), ESLint ✅ (#165), appSetId ✅ (#164); WS4a/WS4 🟡 в работе. Ре-ревью влитого кода 08.09 — регрессий для живого iOS 1.0.0 нет.
> **Источники:** аудит `Mobile/` на Android-готовность, разбор изоляции платформ в проекте PACE (`rork-pace-app`), [PLAN_RELEASE_v2.md](PLAN_RELEASE_v2.md), [APPSTORE_LAUNCH_PLAN.md](APPSTORE_LAUNCH_PLAN.md), [PUSH_NOTIFICATIONS_AUDIT_AND_SCENARIOS.md](../social/PUSH_NOTIFICATIONS_AUDIT_AND_SCENARIOS.md), [UGC_MODERATION_M2.md](UGC_MODERATION_M2.md)
> **Контекст:** iOS 1.0.0 одобрен Apple 25.08.2026 (собран на SDK 54), `app.json` уже на 1.0.1 и на SDK 57. Android не собирался ни разу. `tsc --noEmit` на `chore/expo-57` чистый.

---

## 0. TL;DR

**Что показал аудит.** Каркас в порядке: CNG без закоммиченных `ios/`/`android/`, единственный iOS-only нативный модуль (`modules/device-metrics`) объявлен `platforms: ["apple"]` и на Android не линкуется, бэкенд-пуши платформо-агностичны через Expo Push, Apple-вход гейтится, Google-вход выключен на обеих платформах намеренно. Нет IAP, нет SF Symbols, нет `.ios.tsx`.

**Что показало adversarial review.** Первая редакция утверждала «переписывать нечего» — это неверно. На Android **не работают** шесть мест с `Alert.prompt` (создание и переименование папок — кнопки молча ничего не делают), Android-`Alert` режет меню до трёх кнопок (из меню чата пропадают «Пожаловаться» и «Заблокировать», а это требование Play UGC-policy), ни один из 23 bottom-sheet не закрывается системной кнопкой «Назад», редирект Discogs OAuth уезжает в экран «Страница не найдена», системная тёмная тема ломает палитру иконок. Это ~5–7 дней работы, которых в первой редакции не было.

**Что угрожает iOS прямо сейчас, независимо от Android.**
1. Один OTA-канал `production` + одна `runtimeVersion` + автопроверка при старте: любой Android-хотфикс через `eas update` молча приезжает на iOS 1.0.1. Нужен отдельный Android-канал **до первого Android-билда**.
2. Legacy-ключ `splash` на SDK 57 плагином не читается. **Проверено чистым prebuild:** imageset для splash не создаётся вовсе, storyboard ссылается на несуществующую картинку — iOS 1.0.1 стартовал бы с пустым фоном вместо логотипа. Починено в WS0b: плагин `expo-splash-screen` с `enableFullScreenImage_legacy` даёт storyboard, идентичный SDK 54, и картинку пиксель-в-пиксель.
3. CI для мобилки: git-корень — `Cursor/`, а не `Вертушка/`; workflow с `paths: Mobile/**` не запустится никогда, PR будет «зелёным» пустотой.

**Четыре слоя работы:**

| Слой | Что | Объём |
|---|---|---|
| Страховка iOS | OTA-каналы врозь, CI с `tsc` в правильном корне и baseline для prebuild-диффа, splash-фикс, ветка из `origin/main` | 1.5 дня |
| Инфраструктура | Play-аккаунт (вопрос страны и карты), Firebase/FCM, service account, `eas.json`, эмулятор на маке | 2 дня + верификация Google 2–5 рабочих дней |
| Код | Backend-конфиг по платформам + веб-страница удаления аккаунта, notification channel, визуал (blur/тени/клавиатура/edge-to-edge), паритет взаимодействий (prompt/action sheet/back/dark mode/OAuth-редирект), ассеты | 8–11 дней |
| Магазин | Listing руками (EAS Metadata Play не умеет), data safety, IARC, ToS-гейт для UGC, closed testing 14 дней × 12 тестеров, заявка на production и её ревью ≤7 дней | 3 дня работы + **~3 недели календаря** |

**Критический путь — Google, не код:** верификация аккаунта (2–5 раб. дней) → closed testing 14 дней непрерывно с 12 opt-in тестерами → заявка на production access → ревью до 7 дней. Итого **4–5 недель** от старта при ~12 рабочих днях кода. Единственный рычаг — завести аккаунт и набрать тестеров в день 1. Билд для closed testing должен уже содержать фиксы папок, меню и OAuth, иначе тестеры выпадут из пула и 14 дней начнутся заново.

---

## 1. Принципы изоляции (что берём из PACE)

В `rork-pace-app` нет написанной «стратегии изоляции» — она получается структурно. Пять приёмов оттуда плюс три наших.

### П1. Никогда не коммитить `ios/` и `android/` (CNG)
Нативные проекты генерируются `expo prebuild` из `app.json` + config-плагинов. Android-работа физически не может испортить iOS-нативку, потому что её нет в git.
**Вертушка:** ✅ `Mobile/.gitignore:41-42` игнорирует оба каталога, `git ls-files ios android` пуст. Локальный `Mobile/ios/` протух (03.08, SDK 54, содержит поды от выключенного Google Sign-In) — перед фиксацией baseline пересоздать `--clean`.
**Правило:** так и остаётся. Нативные правки — только через config-плагин или локальный Expo-модуль.

### П2. Один локальный Expo-модуль, две нативные папки, один TS-фасад
PACE: `modules/pace-live-activity/` → `"platforms": ["ios","android"]`, Swift в `ios/`, Kotlin в `android/`, один `index.ts`.
**Вертушка:** `modules/device-metrics/` → `platforms: ["apple"]`, `lib/deviceMetrics.ts:35` возвращает `null` вне iOS. Термальную телеметрию на Android **не делаем в этом релизе**; если понадобится — `android/` папка в том же модуле, iOS-часть не открывается.

### П3. `requireOptionalNativeModule` + no-op фолбэки
Фасад возвращает безопасный дефолт, если натив не слинкован; ошибки логируются, не бросаются.
**Вертушка:** ✅ уже так в `lib/deviceMetrics.ts`, `SocialAuthButtons.tsx`, `lib/reviewPrompt.ts`, `MascotIntro.tsx`, `MascotLoader.tsx`.
**Правило:** любой новый платформенно-зависимый кусок — фасад в `lib/` или `components/ui/` с гвардом внутри. Экраны в `app/` не пишут `Platform.OS` для capability-гейтов.

### П4. Гвард внутри сервиса, не на каждом вызове
PACE: `ensureAndroidPushChannel()` начинается с `if (Platform.OS !== 'android') return;`, вызывается безусловно. Так же делаем channel в `lib/push.ts`.

### П5. Платформенное расхождение — токен, не ветка в компоненте
**Поправка после ревью:** токен теней в Вертушке **уже есть** — `constants/theme.ts:476-527` экспортирует `Shadows.{xs,sm,md,lg,tabBar,glow,glowEmber}` с `shadow*` и `elevation` вместе; RN сам игнорирует чужие ключи на каждой платформе, так что `Platform.select` не нужен. Работа — не «внедрить токен», а перевести ~14 ad-hoc стилей без `elevation` на `Shadows.*` и починить `glow*` (у них `elevation: 0`, на Android свечение исчезает).

### П6 (наш). Android — явное решение, а не else-ветка
Бинарный `Platform.OS === 'ios' ? A : B` делает Android невидимым дефолтом. Для новых мест — `Platform.select({ ios, android, default })`. **Но не переписывать существующие ради формы**: каждое касание общего кода — это диф на iOS.

### П7 (наш). Платформенный компонент — alias модуля, не wrapper
Из ревью: обёртка `<View><BlurView/></View>` или неполный проброс props ломает клип и flex на iOS. Правильная форма:
```ts
export const BlurViewCompat: ComponentType<BlurViewProps> =
  Platform.OS === 'ios' ? BlurView : AndroidGlass;
```
iOS-дерево байт-в-байт прежнее. То же для `ActionSheetCompat` и `PromptSheet`: на iOS остаются `ActionSheetIOS`/`Alert.prompt`, Android получает bottom sheet.

### П8 (наш). Страховка iOS до первой Android-правки
CI с `tsc --noEmit` — потому что после апгрейда SDK 57 именно `tsc` находил рантайм-баги (`SDK_UPGRADE_CHECKLIST.md`). Плюс baseline-дифф iOS-конфига (§2.4) и раздельные OTA-каналы (§2.5).

---

## 2. Инвариант «iOS не трогаем» — формально

1. **Ветка.** `git fetch && git worktree add /Users/vladislavrumancev/Cursor/.wt-android -b feat/android-port origin/main`. Не от локального `main` — он отстал на 67 коммитов и выписан в другой worktree (`~/vertushka-onboarding`). Перед этим закоммитить/влить грязные 36 файлов `chore/expo-57` поимённо (там `lib/api.ts` и `lib/types.ts`, которые трогает WS2). `git worktree prune` (5 висячих).
2. **CI-гейт.** Workflow в `/Users/vladislavrumancev/Cursor/.github/workflows/mobile-ci.yml` (git-корень — `Cursor/`; образец — `backend-tests.yml` там же): `paths: ["Вертушка/Mobile/**", ".github/workflows/mobile-ci.yml"]`, `working-directory: Вертушка/Mobile`, `cache-dependency-path: Вертушка/Mobile/package-lock.json`. Джоб — `npm ci` → `npx tsc --noEmit`. ESLint **пока не гейт**: конфига и пакета нет (`package.json:69-74`), `npx eslint .` упадёт; заводится отдельным PR через `npx expo lint`. Чек сделать required в branch protection, иначе «PR не мерджится» — декларация.
3. **Файловый периметр.** Без отдельного ревью: `app.json` секция `android`, `eas.json` секции `android`, `plugins/*Android*.js` (новые файлы, `withDangerousMod(['android', …])`; существующий iOS-плагин не открывать), `lib/push.ts` (гвард внутри), `assets/` (новые Android-ассеты), `Backend/app/web/` (страница удаления аккаунта, assetlinks). **С ревью и регрессионным тестом:** `Backend/app/api/app_config.py` и `services/app_config.py` — их читает каждый холодный старт iOS (`lib/remoteConfig.ts:39`). Всё в `components/` и `app/` — только через alias-паттерн П7 или `Platform.select` с неизменной iOS-веткой; на ревью диф проверяется именно на это.
4. **Baseline iOS-конфига.** `git diff Podfile.lock` невозможен — `ios/` не в git. Вместо этого коммитим `Mobile/ci/ios-baseline/` (Podfile.properties.json, Info.plist, Expo.plist, entitlements, SplashScreen.storyboard из чистого `prebuild -p ios --clean`) и `Mobile/ci/ios-introspect.baseline.json` (`npx expo config --type introspect --json | jq .ios`). CI на ubuntu делает `prebuild -p ios --no-install` (валидно: pods пропускаются вне darwin) и диффит с baseline. Обновление baseline — только в PR с меткой `ios-config-change`. Ограничение: плагины, которые срабатывают только при `pod install`, гейт не увидит.
5. **OTA-каналы врозь.** `eas.json`: `production.android.channel = "production-android"`, iOS остаётся `production` (канал вшит в отгруженные бинарники, менять нельзя). `package.json`: `update:prod:ios` = `eas update --channel production --platform ios`, `update:prod:android` = `--channel production-android --platform android`; общий `update:prod` удалить. Правило: iOS-канал получает только `--platform ios` апдейты из PR без метки `android`.
6. **Одна кнопка отката.** Один PR = одна тема; Android-правки не смешивать с рефакторингом. Любой WS обратим одним `git revert`.

---

## 3. Аудит: что есть, что сломано

### Уже готово
- `app.json` → `android`: `package: com.vertushka.app`, `adaptiveIcon`, `permissions: CAMERA` (с дублем), `blockedPermissions: RECORD_AUDIO`
- `eas.json` → `submit.production.android` есть, но путь к ключу указывает на FCM-файл вместо service-account
- Push: бэкенд через Expo Push API; `lib/push.ts` обрабатывает Android 13+ `POST_NOTIFICATIONS`; схема `PushTokenUpdate` с `extra=ignore` — новое поле со старого бэка не уронит
- Auth: email работает; Apple iOS-only с гейтом; Google выключен на обеих (`react-native.config.js` + `expo.autolinking.exclude`) по юридической причине — не включать
- `Share.share({url})` на Android игнорирует `url`, но все места дублируют ссылку в `message` — деградирует мягко
- `Modal` — все 18 с `onRequestClose`
- Никаких `.so` в `node_modules`: требование 16 KB page size (Android 15+) закрыто AAR-ами Expo/RN
- `remoteConfig` fail-open, парсинг ответа нестрогий (`lib/types.ts:1215` plain interface) — расширение `/api/config/` не уронит iOS 1.0.0/1.0.1

### Ломает пользователя на Android (критично)
| # | Что | Где |
|---|---|---|
| B1 | `store_url` = App Store для всех; force-update на Android — тупик | `Backend/app/config.py:279`, `api/app_config.py:67`, `Mobile/components/ForceUpdateScreen.tsx:22,41` |
| B2 | Единый `min_supported_version`; бамп «под Android» блокирует всех iOS | `services/app_config.py:122-145`, `api/app_config.py:107-121` |
| B3 | Нет FCM: Firebase-проекта, `google-services.json`, `android.googleServicesFile` | `app.json` |
| B4 | Нет notification channel — на Android 8+ пуши без звука и heads-up; на 13+ без канала не появится даже запрос разрешения | `lib/push.ts`, `Backend/app/services/push.py:146-151` (нет `channelId`) |
| B5 | `Alert.prompt` — iOS-only, на Android молча no-op: создание/переименование папок мертво | `app/(tabs)/collection.tsx:680,692`, `app/folder/[id].tsx:86`, `app/wishlist-folder/[id].tsx:91`, `components/FolderPickerModal.tsx:125`, `WishlistFolderPickerModal.tsx:115` |
| B6 | `Alert.alert`-фолбэк для `ActionSheetIOS` режет до 3 кнопок; в чате из 6 пунктов пропадают report/block — нарушение Play UGC-policy | `app/messages/[conversationId].tsx:1690` (6), `profile.tsx:226` (4), `record/manual.tsx:123` (4), `notifications.tsx:270`, `settings/notifications.tsx:87` |
| B7 | Discogs OAuth: редирект `vertushka://discogs-callback` на Android приходит интентом в `MainActivity`, expo-router ведёт в `+not-found` | `app/settings/discogs.tsx:259`, `SocialAuthButtons.tsx:151`, нет `app/+native-intent.ts` |
| B8 | Нет `BackHandler` нигде; 23 `@gorhom/bottom-sheet` и кастомные оверлеи не закрываются кнопкой «Назад» — она уводит с экрана | `grep BackHandler app components lib` = 0 |
| B9 | `eas.json` без Android build-профилей | `eas.json` |
| B10 | Нет CI | `Cursor/.github/workflows/` — только `backend-tests.yml` |

### Деградация UX (высокие)
| # | Что | Где |
|---|---|---|
| H1 | `BlurView` без Android-фолбэка в 6 компонентах, включая `GlassTabBar` и меню report/block в чате | `GlassTabBar.tsx:97,166`, `record/[id].tsx:1284,1310,1345`, `market/store/[slug].tsx:243`, `MessageContextMenu.tsx:145`, `MarketHeader.tsx:82`, `MarketSearchInput.tsx:59`; `BlurViewCompat` только в `onboarding.tsx:355` и принимает только `children` |
| H2 | `userInterfaceStyle: "light"` на Android не действует без `expo-system-ui`; `Icon.tsx:427-441` берёт палитру из `useColorScheme()` → тёмные иконки на светлом фоне | `app.json:9`, `components/ui/Icon.tsx` |
| H3 | Edge-to-edge (в SDK 57 обязателен, ключ `edgeToEdgeEnabled` — deprecated no-op с варнингом): `GlassTabBar` `bottom: 28` хардкод, 5 `Modal statusBarTranslucent` без `navigationBarTranslucent`, 12 module-level `Dimensions.get('window')` | `GlassTabBar.tsx:156`, `RootOverlay.tsx:87`, `MessageContextMenu.tsx:136`, `ImageLightbox.tsx:156`, `WishlistDigestSheet.tsx:392`, `AchievementsTourOverlay.tsx:74`, `Confetti.tsx:9`, `ZoomableRecordGrid.tsx:88` |
| H4 | Клавиатура: диагноз первой редакции («`behavior={undefined}` — баг») скорее неверен — при дефолтном `softwareKeyboardLayoutMode: resize` это правильная идиома, а `android: 'height'` даст двойной сдвиг. Реальная зона риска — чат с `useAnimatedKeyboard()` под edge-to-edge и `keyboardWillShow` в `manual.tsx` | `messages/[conversationId].tsx:870`, `record/manual.tsx:205`, 4 KAV-экрана |
| H5 | Legacy `splash` не применяется на SDK 57 — iOS 1.0.1 уже не как одобренный 1.0.0 | `app.json` `splash`, плагин `expo-splash-screen` не подключён |

### Средние
M1 нет notification icon (серый квадрат) и `icon`/`color` в плагине · M2 нет monochrome icon (Android 13+) · M3 `Text.defaultProps` clamp масштаба шрифта — no-op на RN 0.86, Android-юзеры чаще ставят 130% (`lib/responsive.ts:69-75`) · M4 `react-native-view-shot` в `Modal` флакает (share-карточка ачивки) · M5 сканер на MLKit vs AVFoundation — точность отличается · M6 `Linking.openURL('mailto:')` без `.catch` (`profile.tsx:728`, `LegalScreen.tsx:60`) · M7 нет `intentFilters`/App Links — share-ссылки `https://vinyl-vertushka.ru/@user` на Android открывают Chrome, не приложение · M8 Amplitude `trackingOptions.appSetId` по умолчанию `true` — влияет на ответ в Data safety · M9 `expo-build-properties` установлен, не в `plugins[]`; при подключении пишет iOS-ключи даже с одним `android`-блоком · M10 Sentry-плагин iOS-only, но для Android gradle-плагин читает env `SENTRY_DISABLE_AUTO_UPLOAD` сам — вероятно, ничего не нужно

### Низкие
L1 дубль `CAMERA` · L2 `adaptiveIcon.backgroundColor #ffffff` ≠ splash `#FAFBFF` · L3 SecureStore не переживает переустановку на Android → логаут (ожидаемо, в FAQ) · L4 Lottie 1.8 МБ на слабых устройствах · L5 неиспользуемый `SpaceMono-Regular.ttf` · L6 `users.push_token` без `push_platform` — не различить платформы; один токен на юзера (last-wins) · L7 `RootOverlay` Android-ветка не прогонялась · L8 Hermes ICU для ru-RU даёт U+00A0 в разрядах, iOS — U+202F; косметика, `.replace(/,/g,' ')` в `user/[username]/index.tsx:102,126,145` это скрывает

---

## 4. Workstream'ы

Каждый WS — кандидат в чип. Порядок = зависимости. WS0, WS0b, WS1 стартуют в день 1.

### WS0 — Страховка iOS: OTA-каналы, CI, baseline, ветка ✅ 2026-09-07
**Файлы:** `Cursor/.github/workflows/mobile-ci.yml` (новый), `Mobile/eas.json` (каналы), `Mobile/package.json` (скрипты `typecheck`, `update:prod:ios`, `update:prod:android`), `Mobile/ci/ios-baseline/*`, `Mobile/ci/ios-introspect.baseline.json`
**Объём:** §2.1 (worktree от `origin/main`), §2.2 (CI в правильном корне, только `tsc`), §2.4 (baseline после `rm -rf Mobile/ios && prebuild -p ios --clean`), §2.5 (каналы и скрипты). Branch protection: required check.
**Приёмка:** PR с намеренно сломанным типом — красный; PR с правкой `ios.infoPlist` без метки — красный на baseline-диффе; `eas channel:list` показывает `production-android`.
**Сделано:** `Cursor/.github/workflows/mobile-ci.yml` (jobs `typecheck` и `ios-config-guard`), `Mobile/ci/{check,update}-ios-baseline.sh` + `snapshot-ios.sh`, baseline в `Mobile/ci/ios-baseline/` (Info.plist, entitlements, PrivacyInfo, storyboard без id, Podfile, Podfile.properties.json, Expo.plist, AppDelegate, манифест ассетов с md5, срез `expo config --type introspect`). Негативный тест: подмена `infoPlist` красит гейт. `eas.json`: `preview.android.channel = preview-android`, `production.android.channel = production-android` (проверено `eas config`). Скрипты `update:prod:ios` / `update:prod:android`, `typecheck`. Worktree `Cursor/.wt-android` от `origin/main`. Branch protection на `main` пока нет — required check включить руками в GitHub после первого зелёного прогона.
**Оценка:** 1 день.
**Отдельно, до WS0:** PR `npx expo lint` — завести ESLint-конфиг, погасить baseline-варнинги, потом добавить в CI.

### WS0b — Splash-фикс для iOS (iOS-only PR, до билда 1.0.1) ✅ 2026-09-07
**Файлы:** `Mobile/app.json` (плагин `expo-splash-screen`)
**Объём:** `["expo-splash-screen", {"image": "./assets/images/splash-icon.png", "resizeMode": "contain", "backgroundColor": "#FAFBFF", "ios": {"enableFullScreenImage_legacy": true}}]`; сверить в симуляторе с TestFlight 1.0.0 (SDK 54, `SplashScreenLegacy.imageset`). Android-секция добавляется потом в WS6 к зафиксированному baseline.
**Приёмка:** iOS-splash визуально совпадает с 1.0.0; `prebuild -p ios` подтверждает, что плагин применился (в `pluginHistory` появился `expo-splash-screen`).
**Оценка:** 0.5 дня. **Это фикс iOS-регрессии, он нужен вне зависимости от Android.**

### WS1 — Play Console + Firebase + ассеты (владелец, день 1, критический путь)
**Владелец:** Влад. Claude готовит инструкции и валидирует файлы.
**Решение перед стартом — страна аккаунта (Q1):** регистрация из России возможна (Google публикует RU-специфичную верификацию по паспорту и адресу), но российской картой 25 $ не оплатить; несовпадение страны профиля, карты и VPN — известный триггер бана. Варианты: (а) бразильский аккаунт, если есть бразильские документы и карта (Apple-аккаунт уже бразильский); (б) российский профиль + российский паспорт и адрес + чужая нероссийская карта — путь сообщества с документированным риском. Не смешивать. D-U-N-S для персонального не нужен; телефон и 2SV обязательны.
**Объём:**
- Аккаунт → верификация личности (2–5 рабочих дней) → приложение `com.vertushka.app` (запись создаётся руками, `eas submit` может залить первый AAB сам — ручная первая загрузка больше не требуется)
- **Сразу** closed testing track и список 12 тестеров: opt-in по ссылке, установка под тем же Google-аккаунтом; выход/вход тестера сбрасывает 14-дневный счётчик. Список собрать сегодня (коллекционеры из чатов, друзья)
- Service account в Cloud-проекте: роли в Play Console — View app information; Edit/delete draft apps; Release to production; Release to testing tracks; Manage testing tracks/testers; Manage store presence; включить Google Play Android Developer API. JSON → `Mobile/play-service-account.json` (gitignore) + EAS file-secret. Тот же аккаунт можно дать FCM-права и использовать для пушей
- Firebase: проект, Android-app `com.vertushka.app`, `google-services.json` → `Mobile/` (коммитить **можно**, там только публичные идентификаторы; секрет — service-account). FCM v1 key: `eas credentials -p android` → Google Service Account → FCM V1. SHA-отпечатки для FCM не нужны
- Play App Signing: принять дефолт при первой загрузке (Google-generated key); upload key — EAS-managed. Потеря upload key восстановима, своего signing key — нет
- Дизайн-задание в день 1 (иначе WS6 заблокирован): notification icon 96×96 белый на прозрачном, monochrome icon, Android-splash (иконка ≤200 dp, не full-bleed), feature graphic 1024×500, иконка 512×512
**Приёмка:** аккаунт верифицирован; closed track с ≥12 приглашёнными; оба JSON локально и в EAS; `eas credentials -p android` показывает FCM key и keystore.
**Оценка:** 1 день работы + 2–5 рабочих дней ожидания Google.

### WS2 — Backend: конфиг по платформам, удаление аккаунта, push_platform (B1, B2, L6) ✅ 2026-09-07
**Файлы:** `Backend/app/config.py`, `api/app_config.py`, `services/app_config.py`, `schemas/app_config.py`, `schemas/user.py:140-142`, `models/user.py:150`, `api/users.py:608` (`PUT /me/push-token`), `web/routes.py:666`, новый шаблон `web/templates/delete_account.html`, alembic-миграция, `tests/test_app_config.py:156` (проверка `set(body)` упадёт на новых ключах — обновить); Mobile: `lib/remoteConfig.ts:43`, `lib/version.ts`, `lib/types.ts:1215`, `components/ForceUpdateScreen.tsx` (`accessibilityLabel` параметризовать, iOS-строку не менять)
**Дизайн `GET /api/config/`** — обе платформы в ответе, legacy-поля остаются и жёстко равны iOS:
```json
{
  "min_supported_version": "1.0.0", "store_url": "https://apps.apple.com/...",
  "platforms": {
    "ios":     {"min_supported_version": "1.0.0", "store_url": "https://apps.apple.com/app/id6774999020"},
    "android": {"min_supported_version": "1.0.1", "store_url": "https://play.google.com/store/apps/details?id=com.vertushka.app"}
  }
}
```
- `platform` — **обязательное** поле `MinVersionUpdateRequest`, раздельные Redis-ключи. Тест: «бамп android не меняет legacy и ios»
- Клиент: `platforms?.[Platform.OS] ?? legacy`
- Web-CTA: Play-бейдж за фичефлагом `PLAY_STORE_PUBLISHED`
- **Веб-страница удаления аккаунта** `vinyl-vertushka.ru/delete-account` — обязательна для Play при наличии регистрации: шаги, что удаляется/что остаётся и на сколько, контакт. Ссылка идёт в Data safety → Data deletion. In-app удаление уже есть
- `users.push_platform` (nullable `ios|android`), клиент шлёт при регистрации токена. Один токен на юзера (last-wins) — для v1 приемлемо, задокументировать
- После ребейза — `alembic heads` (два head'а git не ловит)
**Приёмка:** тесты на форму ответа и на изоляцию бампа; `ForceUpdateScreen` на Android открывает Play URL; страница удаления открывается без логина.
**Оценка:** 1.5 дня.

### WS3 — Пуши на Android (B3, B4, M1)
**Файлы:** `app.json` (`android.googleServicesFile`; плагин `expo-notifications` с `icon`, `color`, `defaultChannel: "default"`), `lib/push.ts`, `assets/images/notification-icon.png`, `Backend/app/services/push.py:146-151` (`channelId`)
**Объём:** `ensureAndroidPushChannel()` по П4, **вызывается до** `getExpoPushTokenAsync` (на Android 13+ без канала не появится запрос разрешения); константа `ANDROID_PUSH_CHANNEL_ID = 'default'`, бэкенд кладёт `channelId` в каждый пуш; контракт зафиксирован комментарием в обоих репо. Один канал на старте; разделение по типам — вторая итерация. `useNextNotificationsApi` — устаревший флаг, не добавлять.
**На iOS:** `setNotificationChannelAsync` — no-op, `channelId` APNs-путём игнорируется, плагин на iOS читает только `mode/sounds`. Безопасно.
**Приёмка:** на физическом Android через `expo push:send` пуш со звуком и баннером в фоне и при убитом приложении; иконка корректна на светлой и тёмной шторке. Remote push в Expo Go недоступен — только dev-build.
**Оценка:** 1 день после WS1.

### WS4 — EAS-профили, build-properties, первый prebuild (B9, M9, M10, L1)
**Файлы:** `eas.json`, `app.json` (`plugins` → `expo-build-properties`, `expo-system-ui`), `package.json`
**Объём:**
- `eas.json`: `development.android = {buildType: "apk"}`, `preview.android = {buildType: "apk"}`, `production.android = {buildType: "app-bundle", channel: "production-android"}`; `submit.production.android.serviceAccountKeyPath = "./play-service-account.json"`, `track: "internal"`
- `eas build:version:set -p android` — начальный `versionCode` (например 1010), иначе первый билд с `appVersionSource: remote` + `autoIncrement` встанет на промпте
- `expo-build-properties`: **только** `{"android": {"minSdkVersion": 26}}` (дефолт RN 0.86 — 24; 26 = Android 8, порог notification channels). **Не пиновать `targetSdkVersion`/`compileSdkVersion`**: Play с 31.08.2026 требует target 36, SDK 57 уже даёт 36/36/AGP 8.12/Kotlin 2.1.20/NDK 27.1. Плагин всё равно запишет iOS-ключи в `Podfile.properties.json` (`forceStaticLinking`, `privacyManifestAggregationEnabled`, `EXPO_USE_PRECOMPILED_MODULES`) — поведение не меняет, но baseline из WS0 покраснеет: принять осознанно в этом PR с меткой `ios-config-change`
- `npx expo install expo-system-ui` — иначе `userInterfaceStyle: light` на Android не действует (H2)
- Убрать `edgeToEdgeEnabled` из `app.json` (deprecated, варнинг при prebuild; edge-to-edge в SDK 57 обязателен, отключить нельзя)
- Убрать дубль `CAMERA`
- Sentry: проверить локальный `expo run:android` с env `SENTRY_DISABLE_AUTO_UPLOAD` из dev-профиля; плагин расширять только если упадёт, и **отдельным файлом** `withSentryDisableLocalUploadAndroid.js`
- `npx expo prebuild -p android --clean`, поднять на эмуляторе, падения — в BUGS.md с тегом `[android]`
**Приёмка:** `eas build -p android --profile preview` зелёный, APK ставится, приложение доходит до логина; `eas build -p ios --profile preview` тоже зелёный; baseline обновлён.
**Оценка:** 1.5–2 дня.

### WS4a — Android-эмулятор на маке (чтобы Claude проверял сам, без телефона)
Сейчас на маке нет ни SDK, ни JDK, ни эмулятора. Ставится без Android Studio; JDK 17 (RN 0.86 рекомендует именно 17, старше — проблемы). Требует установки ПО — только после подтверждения на синке (Q11).
```bash
brew install --cask zulu@17 android-commandlinetools
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH
yes | sdkmanager --licenses
sdkmanager "platform-tools" "emulator" "platforms;android-36" "build-tools;36.0.0" \
  "ndk;27.1.12297006" "system-images;android-36;google_apis;arm64-v8a"
avdmanager create avd -n pixel8_api36 -k "system-images;android-36;google_apis;arm64-v8a" --device "pixel_8"
emulator -avd pixel8_api36 -gpu host &
cd Mobile && npx expo run:android
```
`JAVA_HOME`/`ANDROID_HOME` в `~/.zshrc`; при конфликте JDK — `org.gradle.java.home` в `~/.gradle/gradle.properties`. NDK 27.1 обязателен, без него локальный prebuild падает. Образ `google_apis` (не `playstore`) — рутуемый; FCM в нём работает.
**Что даёт:** прогон WS5/WS7, скриншоты через `adb exec-out screencap`, логи через `adb logcat`, второй AVD с API 29 для нижней границы. **Чего не даёт:** сканер штрихкодов (виртуальная камера), Doze/MIUI, тепло, производительность на бюджетнике — для этого WS7 на железе.
**Оценка:** 0.5 дня, ~4 ГБ.

### WS5a — Визуал: blur, тени, клавиатура, edge-to-edge (H1, H3, H4, П5) 🟡 код 2026-09-07, железо → WS7
**Файлы:** `components/ui/BlurViewCompat.tsx` (новый, alias по П7; `AndroidGlass` = полупрозрачный `View` + `LinearGradient`, принимает полный `BlurViewProps`), 6 компонентов с `BlurView`, `onboarding.tsx` (перевести на общий), ~14 стилей без `elevation`, `constants/theme.ts` (`glow*` → `boxShadow`, RN ≥0.76 с New Arch), `GlassTabBar.tsx:156`, 5 `Modal` (+`navigationBarTranslucent`), `InAppNotificationToast.tsx`, sticky-CTA `user/[username]/index.tsx:1569`
**Объём:**
- **Blur:** alias-паттерн, iOS-дерево не меняется; snapshot-тест `GlassTabBar` через `react-test-renderer` (уже в devDeps) с iOS-моком до/после. `@react-native-community/blur` не тянем
- **Тени:** не вводить новый токен (он есть). Перевести ad-hoc стили без `elevation` на `Shadows.*`; `glow`/`glowEmber` → `boxShadow`; проаудировать `overflow: 'hidden'` + `elevation` (88 мест `overflow: hidden`) — на Android `elevation` клипуется и требует непрозрачного фона
- **Клавиатура:** сначала решить `android.softwareKeyboardLayoutMode` (дефолт `resize` = `adjustResize`; с ним `KeyboardAvoidingView behavior={undefined}` на Android — правильно, `'height'` **не добавлять**). Затем на устройстве проверить 4 KAV-экрана, чат с `useAnimatedKeyboard()` (опции `isStatusBarTranslucentAndroid`/`isNavigationBarTranslucentAndroid`), `manual.tsx` события
- **Edge-to-edge:** `useSafeAreaInsets().bottom` вместо `bottom: 28` в `GlassTabBar` (3-кнопочная навигация — 48 dp); `navigationBarTranslucent` на 5 `Modal`; проверить 12 `Dimensions.get('window')` на module-level; прогон на жестовой и 3-кнопочной навигации
**Приёмка:** скриншот-сравнение iOS/Android на 8 экранах (главная, скан, коллекция, карточка, маркет, профиль, сообщения, ачивка); ничего под системными панелями; клавиатура не перекрывает поля; iOS-скриншоты до/после идентичны; snapshot-тест зелёный.
**Оценка:** 3 дня.
**Сделано (код, 2026-09-07, PR `feat/android-ws5a-visual`; на устройстве НЕ прогонялось — нет эмулятора, см. WS4a):**
- **Blur:** `components/ui/BlurViewCompat.tsx` — alias по П7 (`Platform.OS === 'ios' ? BlurView : AndroidGlass`); `AndroidGlass` = `View` с подложкой по `tint` (light/dark/default), `intensity` → alpha (0.25–1.0 от максимума рецепта), 1.5dp градиентная кромка сверху, полный `BlurViewProps`, `style`/`children` без обёрток. Переведены все 7 мест (`GlassTabBar`, `record/[id]` ×3, `market/store/[slug]`, `MarketHeader`, `MarketSearchInput`, `MessageContextMenu`) + локальный `BlurViewCompat` в `onboarding.tsx` удалён в пользу общего (Android-подложка карточки оставлена прежней `rgba(255,255,255,0.18)` через `Platform.select` в стиле — светлый glass слишком плотный под белый текст). `grep "from 'expo-blur'"` в `app/`+`components/` → только `BlurViewCompat.tsx`.
- **Snapshot-гейт:** `__tests__/GlassTabBar.ios.test.tsx` (пресет `jest-expo/ios`, снимок снят до правок, после — совпал). Jest заведён минимально: `jest`, `jest-expo`, `@types/jest` в devDeps, `jest.setup.js` (моки `react-native-worklets`/`react-native-reanimated`/`expo-haptics`), `babel.config.js` (`babel-preset-expo` — тот же дефолт, что у Metro), `npm test`.
- **Тени:** `constants/theme.ts` — `androidShadow({color, opacity, radius, offsetY})` → `Platform.select({ android: { boxShadow }, default: {} })`; `Shadows.glow`/`glowEmber` получили Android-`boxShadow` (elevation 0 оставлен: при offset 0 elevation даёт подложку, а не свечение). `elevation` дописан: `messages/index.tsx` emptyBtn (6), `user/[username]/index.tsx` valueCard (2), dropdownCard (4), confirmBtn (8), `AutoRail.tsx` railCover (4), `InAppNotificationToast.tsx` card (8). Android-`boxShadow` там, где elevation бессилен (offset 0 / нет фона / `overflow: hidden`): `achievements.tsx` seriesProgressFill+Dot, `messages/[conversationId].tsx` emptyAvatar, `OfferBadge.tsx` обе точки, `OfferDetailCard.tsx` cta + cardHighlighted. iOS-ключи нигде не менялись.
- **Edge-to-edge:** `GlassTabBar` — iOS `styles.container` тот же объект (`bottom: 28`), Android `bottom = max(insets.bottom, 16) + 12` из `BottomTabBarProps.insets` + `boxShadow` вместо elevation (у контейнера нет фона → elevation тень не рисует). `navigationBarTranslucent` добавлен к 5 `Modal` (`RootOverlay`, `AchievementsTourOverlay`, `ImageLightbox`, `MessageContextMenu`, `WishlistDigestSheet`). `InAppNotificationToast` (`insets.top + 8`) и sticky-CTA в `user/[username]/index.tsx` (`insets.bottom + 12`) уже на инсетах — без правок. Module-level `Dimensions.get('window')` (12 мест) edge-to-edge не ломает: под e2e `window` = полный экран, ширина от панелей не зависит, высота используется только как стартовый viewport (`ZoomableRecordGrid`) и конец траектории конфетти (`Confetti`) — оба терпимы к ±48dp. Риск другой — не обновляется при повороте/split-screen (у нас portrait-lock) — в WS7.
- **Клавиатура:** `softwareKeyboardLayoutMode` не задан = `resize`; `behavior={undefined}` на Android в 4 KAV оставлен, `'height'` не добавлен. `manual.tsx` слушает `keyboardDidShow/Hide` на Android — правильно (`keyboardWill*` на Android не приходят). `messages/[conversationId].tsx`: `useAnimatedKeyboard({ isStatusBarTranslucentAndroid: true, isNavigationBarTranslucentAndroid: true })` — по докам reanimated обязательны под edge-to-edge, на iOS игнорируются; `paddingBottom = max(height − insets.bottom, 0)` с ними считается как на iOS. Всё это — проверка на железе, см. WS7.
- **Не тронуто (в WS7 глазами):** динамические `shadowColor`-свечения без Android-аналога — `radar.tsx` coverRing/beam, `AchievementPin.tsx` aura, `AchievementsHero.tsx` progressFill, `VinylColorTag.tsx` (анимированный `shadowOpacity` через reanimated), `SwipeTab.tsx` (анимированный glow), `onboarding.tsx` card (тень клипуется `cardBlur overflow: hidden` и на iOS). `overflow: 'hidden'` + `elevation` без `backgroundColor` (elevation, вероятно, не рисуется): `radar.tsx` coverRing, `ManualAddVinylToggle.tsx` pill; с фоном (`AutoRail` railCover, `MarketCarouselCard` coverWrap, `OffersDrawer` container, `MessageContextMenu` actions) — должно быть ок.

### WS5b — Паритет взаимодействий: prompt, action sheet, back, OAuth-редирект, dark mode (B5–B8, H2, M3, M6)
**Файлы:** `components/ui/PromptSheet.tsx` (новый), `components/ui/ActionSheetCompat.ts` (новый), `lib/useAndroidBackClose.ts` (новый), `app/+native-intent.ts` (новый), `lib/responsive.ts`, 6 мест `Alert.prompt`, 8 мест `ActionSheetIOS`, обёртка bottom-sheet + `RootOverlay`, `profile.tsx:728`, `LegalScreen.tsx:60`
**Объём:**
- **`PromptSheet`:** bottom sheet + `TextInput`; на iOS по П7 остаётся `Alert.prompt` (или тоже sheet — решение Q6; iOS-диф нулевой только в первом варианте). Образец — `ThresholdSheet.tsx`, где это уже сделано для одного случая
- **`ActionSheetCompat`:** iOS = `ActionSheetIOS.showActionSheetWithOptions` как есть; Android = bottom sheet со списком, без лимита в 3 пункта; `destructiveButtonIndex`/`cancelButtonIndex` поддержать. Заменить 8 мест; report/block в чате **обязаны** быть видны и подписаны (Play-ревьюер отклоняет неявные)
- **`useAndroidBackClose(isOpen, close)`:** `BackHandler.addEventListener` с гвардом по платформе, вшить в обёртку bottom-sheet и `RootOverlay`. Решить `predictiveBackGestureEnabled` для target 36 (Q7)
- **`+native-intent.ts`:** `redirectSystemPath` глотает `discogs-callback` (возвращает текущий путь), чтобы `openAuthSessionAsync` получил результат, а роутер не ушёл в `+not-found`
- **Dark mode:** после `expo-system-ui` (WS4) проверить `Icon.tsx` — либо палитра от `MODE` из `theme.ts`, либо принять системную; сценарий «системная тёмная тема ON» в WS7
- **Масштаб шрифта:** заменить мёртвый `Text.defaultProps` на обёртку с `maxFontSizeMultiplier` — фикс общий, но Android его вскрывает; сценарий «130%» в WS7
- `mailto:` — `.catch` + тост
**Приёмка:** на эмуляторе/устройстве: создание папки работает, меню чата показывает все 6 пунктов, «Назад» закрывает любой sheet/оверлей, Discogs-вход завершается без «Страница не найдена», тёмная системная тема не меняет вид приложения. iOS: snapshot/визуал без изменений.
**Оценка:** 3–4 дня. **Должен войти в билд для closed testing.**
**Статус 2026-09-07 (код, без устройства):** `lib/promptCompat.ts` + `components/ui/PromptSheet.tsx` (6 мест `Alert.prompt`), `lib/actionSheetCompat.ts` + `components/ui/OptionsSheet.tsx` (9 мест `ActionSheetIOS`, хост `AndroidSheetsHost` в `_layout.tsx`), `lib/useAndroidBackClose.ts` в 4 gorhom-шитах (кастомные оверлеи и `RootModalOverlay` уже RN `Modal` с `onRequestClose` — хук не нужен), `app/+native-intent.ts`, `Icon.tsx` → `THEME_MODE`, font-scale через metro-alias `react-native` → `lib/fontScale/` (`Text.defaultProps` был no-op), `.catch` на `mailto:`. iOS-ветки — прежние нативные вызовы (Q6). `predictiveBackGestureEnabled` не трогали (Q7). Приёмка на устройстве — WS7.

### WS6 — Ассеты и splash Android (M2, L2)
**Файлы:** `app.json` (плагин `expo-splash-screen` → секция `android`: `image` ≤200 dp, `backgroundColor`, `dark`; `android.adaptiveIcon.monochromeImage`), `assets/images/*`
**Зависит от:** WS0b (iOS-baseline splash зафиксирован), WS1 (дизайн-ассеты готовы).
**Приёмка:** splash на Android 10 и 12+ без белого мигания и кривой маски; monochrome-иконка на Android 13+; safe zone адаптивной иконки 66 dp из 108 соблюдена; iOS-splash не изменился (baseline).
**Оценка:** 0.5 дня + дизайн.

### WS7 — QA на железе (M4, M5, L3, L7, L8)
**Устройства:** флагман (Samsung S / Pixel), середняк (Xiaomi/Redmi — MIUI режет фон и пуши), бюджетник (Android 10–11, 3–4 ГБ). Плюс эмуляторы API 29 и 36.
**Условия:** жестовая и 3-кнопочная навигация; системная тёмная тема ON; масштаб шрифта 130%; экран 7" (планшетный layout не заявляем, но не должен разваливаться).
**Сценарии:** 1) email-регистрация → логин → рефреш → логаут; 2) Discogs OAuth полный круг; 3) EAN-13 на 10 реальных пластинках — hit-rate против iPhone; 4) распознавание обложки; 5) коллекция/вишлист/ручное добавление (клавиатура); 6) создание и переименование папок; 7) меню чата: все пункты, report/block; 8) «Назад» на каждом sheet/оверлее/модалке; 9) пуш: сообщение, бронь подарка — фон, убитое приложение, Doze; 10) share профиля/вишлиста; 11) ачивка: оверлей + share-карточка через view-shot; 12) маркет и click-redirector; 13) force-update (подменить `min_supported_version` для android на стейдже — iOS не должен отреагировать); 14) deep link `vertushka://record/123` из холодного старта; 15) переустановка → ожидаемый логаут; 16) экраны стоимости коллекции/цен — разряды чисел.
**Из WS5a — проверить на устройстве (код написан вслепую, без эмулятора):**
- *Клавиатура:* чат `messages/[conversationId]` — поле ввода прижато к клавиатуре без зазора/перекрытия на жестовой и 3-кнопочной навигации, interactive dismiss не дёргает контент; если зазор = высоте nav bar — снять `isNavigationBarTranslucentAndroid` (или оба флага) в `useAnimatedKeyboard`. `record/manual.tsx` — футер прячется по `keyboardDidShow` (на Android событие приходит после анимации — допустим ли прыжок; если нет — `keyboardDidShow` + `LayoutAnimation`). 4 KAV-экрана (`manual`, `edit-profile`, `search`, `user/[username]` sheet) с `behavior={undefined}`: поля не перекрыты при `adjustResize`.
- *Blur:* `AndroidGlass` — плотность подложки на таб-баре (light 60), маркете (dark 20/24), меню чата (dark 20), карточке записи (light 60), онбординге (0.18 override): читаемость текста, контраст с фоном, кромка не «полоска».
- *Тени/свечение:* `boxShadow` реально рендерится на API 26–36 для `Shadows.glow*`, `OfferBadge`, `OfferDetailCard`, прогресс-баров ачивок, аватара пустого чата; свечения без Android-аналога (см. список «Не тронуто» в WS5a) — решить, нужны ли (radar, аура пина, прогресс героя, `VinylColorTag`, `SwipeTab`).
- *Edge-to-edge:* `GlassTabBar` не залезает под nav bar на обоих типах навигации, тень контейнера видна; 5 `Modal` с `navigationBarTranslucent` — контент под nav bar, но без «белой полосы»; `InAppNotificationToast` под status bar не режется; sticky-CTA профиля над nav bar; module-level `Dimensions` — 7" и split-screen не разваливают сетки (`achievements` 3 колонки, `ZoomableRecordGrid`, `RecordCard`/`ArtistCard`).
**Приёмка:** чеклист на 3 устройствах, баги в `docs/BUGS.md` с тегом `[android]`, P0/P1 закрыты.
**Оценка:** 3–4 дня с фиксами.

### WS8 — Play Store listing и комплаенс
**Файлы:** `Design/playstore/` (новая), `docs/plans/appstore/PLAYSTORE_SUBMISSION_KIT.md` (новый), `lib/analytics.ts` (`appSetId: false`), гейт ToS в мессенджере/регистрации
**Объём:**
- Listing **руками** в Play Console — EAS Metadata Google Play не поддерживает (`store.config.json` секцию `google` не делаем; fastlane `supply` для одного приложения не стоит того). Тексты адаптировать из ASO_KIT: короткое 80, полное 4000, ключевые слова в теле описания
- Графика: иконка 512, feature graphic 1024×500, скриншоты phone (мин. 2, реком. 8) в Android-фреймах — iPhone 1290×2796 переиспользовать нельзя
- **Data safety:** собирается (не «шарится» — Amplitude под DPA и self-hosted GlitchTip = collection, not sharing): Personal info → Email, User IDs; Photos and videos (если кадр обложки уходит на сервер — да); Messages → In-app messages; App activity → App interactions; App info & performance → Crash logs, Diagnostics; Device or other IDs — Firebase installation ID при FCM → декларировать. Amplitude: `adid`/`ipAddress`/`carrier` уже выключены, **добавить `appSetId: false`** (одна строка, поведение не меняет) — иначе App Set ID через Play Services. Шифрование в транзите — да. Ссылка на удаление данных — страница из WS2
- **IARC** content rating — аналог ответов 13+ из ASC
- **UGC-policy:** report контента и пользователей, block для любого 1:1, модерация — есть; **добавить явный accept ToS до первого сообщения** (или на регистрации со ссылкой в потоке) — Play требует явно, `UGC_MODERATION_M2.md` дополнить
- Account deletion URL — из WS2, в Data safety
- Data sources: строка в listing/privacy об атрибуции Discogs и номинативном использовании названий магазинов (Play-policy не ломает, Discogs API ToS — да: не редистрибутировать контент, картинки ≤1/с и ≤1000/день на app id)
- Target API 36 — уже дефолт SDK 57
**Приёмка:** internal testing билд принят без policy-варнингов; closed testing запущен с реальным билдом, содержащим WS5b; через 14 дней подана заявка на production access.
**Оценка:** 2–3 дня работы + 14 дней closed testing + до 7 дней ревью заявки.

### WS9 — Релиз и пострелиз
- Версия: Android выходит **1.0.1**, тем же `runtimeVersion`, что iOS 1.0.1; OTA-каналы врозь (WS0)
- **Staged rollout для первого релиза в Play недоступен** — первый релиз уходит на 100% в выбранных странах. Митигация: узкий список стран на старте (RU + 2–3), расширять руками; поэтапная раскатка — с 1.0.2
- Telegram-алёртинг починить до релиза (он «немой» — ревью на 1000 DAU)
- GlitchTip: фильтр `platform:android`, crash-free по платформе; Amplitude: `platform` в user properties, активационная метрика по платформе
- Первые 48 часов: логи FCM-доставки, `DeviceNotRegistered`, MIUI-жалобы → FAQ
- ROADMAP M2: acceptance criteria, Changelog

### WS10 (опционально, после v1) — App Links
`android.intentFilters` с `autoVerify` + `/.well-known/assetlinks.json` на бэке — чтобы `https://vinyl-vertushka.ru/@user` из share открывал приложение, а не Chrome. ~0.5 дня, Android-only, iOS `associatedDomains` тоже нет — паритет «только scheme».

---

## 5. Порядок и календарь

```
Д1      WS0 CI/каналы/baseline ─┐   WS0b splash iOS ─┐   WS1 аккаунт+тестеры+дизайн (Влад) ──┐
Д2–3    WS2 backend             │                    │   ожидание верификации Google 2–5 р.д. │
Д3–4    WS4 EAS/prebuild + WS4a эмулятор             │                                         │
Д4      WS3 push (после FCM из WS1)                  │                                         │
Д5–7    WS5a визуал     ║ параллельно ║  Д5–8 WS5b паритет                                     │
Д8      WS6 ассеты                                                                             │
Д9–12   WS7 QA + фиксы                                                                         │
Д10–12  WS8 listing → internal → closed testing (билд с WS5b) ─────────────── 14 дней ────────┤
Д26     заявка на production access ─── ревью ≤7 дней ───┤
Д27–33  WS9 production (100%, узкий список стран)
```
**4–5 недель календаря при ~12 рабочих днях кода.** Не сжимается: 14 дней closed testing + ревью заявки не ускоряются. Рычаги: WS1 сегодня; WS5a и WS5b параллельно двумя сессиями (worktree).

---

## 6. Решения от владельца (для синка)

| # | Вопрос | Предложение | Влияет |
|---|---|---|---|
| Q1 | **Страна Play-аккаунта и карта для 25 $** — Бразилия (как Apple) или Россия + чужая карта | Бразилия, если есть документы и карта; не смешивать страны | WS1, весь календарь |
| Q2 | Android — отдельная волна или синхронно с iOS 1.0.1 | Отдельная волна; iOS 1.0.1 не держать | WS9, ROADMAP M2 |
| Q3 | Форма `/api/config/` | Обе платформы в ответе, legacy = iOS, `platform` обязателен в staff-эндпоинте | WS2 |
| Q4 | Blur на Android | Полупрозрачный фолбэк alias-паттерном, без нового SDK | WS5a |
| Q5 | `minSdkVersion` | 26; target не пиновать (36 из коробки) | WS4, WS7 |
| Q6 | `PromptSheet`/`ActionSheetCompat`: iOS оставить нативные диалоги (нулевой диф) или тоже перевести на sheet (единый вид) | Оставить нативные на iOS в этом релизе | WS5b |
| Q7 | `predictiveBackGestureEnabled` для target 36 | Выключено в v1, включить после WS5b-обкатки | WS5b |
| Q8 | `push_platform` в `users` — сейчас | Сейчас, миграция копеечная | WS2 |
| Q9 | Есть ли Firebase-проект / Play-аккаунт / service account | Нужен ответ | WS1 |
| Q10 | Кто делает Android-графику (5 позиций из WS1) | Влад/дизайнер, день 1 | WS6, WS8 |
| Q11 | **Ставить Android SDK + JDK 17 + эмулятор на мак** (brew, ~4 ГБ), чтобы Claude тестировал без телефона | Да | WS4a, WS5, WS7 |
| Q12 | ToS-гейт для UGC: на регистрации или перед первым сообщением | На регистрации (один чекбокс), ссылка в первом диалоге | WS8 |
| Q13 | Тестеры: 12 человек, установка и 14 дней не выходить | Собрать список сегодня | WS1 |
| Q14 | Термальная телеметрия на Android | Не в этом релизе | — |

---

## 7. Что НЕ делаем (явно)

Google Sign-In (юридическая причина) · нативный blur-SDK · термальная телеметрия · планшетный layout · Material-дизайн-система · переписывание всех 68 теней · `Platform.select` ради формы в существующем коде · EAS Metadata для Play · пиновка `targetSdkVersion` · staged rollout первого релиза (недоступен) · fastlane.

---

## 8. Риски плана

| Риск | Вероятность | Митигация |
|---|---|---|
| Бан Play-аккаунта из-за несовпадения страны/карты/VPN | средняя | Q1 решить до регистрации; не смешивать |
| Верификация аккаунта дольше 5 рабочих дней | средняя | Неделя буфера заложена |
| Не набрать 12 тестеров или кто-то выйдет и сбросит 14 дней | высокая для соло-разработчика | 15+ приглашённых, напоминание «не удалять»; билд для них уже с WS5b |
| Android-хотфикс через OTA приезжает на iOS | высокая без WS0 | Каналы врозь + `--platform` в скриптах |
| Splash iOS 1.0.1 отличается от одобренного | реализовалось | WS0b до билда 1.0.1 |
| Prebuild вскрывает несовместимость с New Arch | средняя | Подозреваемые: `react-native-view-shot`, `@gorhom/bottom-sheet`, `lottie-react-native`; `expo-build-properties` для пиновки |
| `expo-build-properties` красит iOS-baseline | гарантировано | Принять в PR WS4 с меткой `ios-config-change` |
| Play отклоняет: UGC без ToS-гейта / нет deletion URL / неявные report-кнопки | средняя | WS2 + WS8, проверить до internal |
| MIUI/Doze режет пуши | высокая на Xiaomi | FAQ, не бороться в v1 |
| Сканер на MLKit хуже AVFoundation | средняя | Замер в WS7; ручной ввод EAN уже есть |
| WS5a/WS5b трогают общий код и ломают iOS | низкая при П7 + snapshot-тесты + baseline | Ревью дифа на неизменность iOS-ветки |

---

## 9. Матрица зависимостей (справочно)

| Зависимость | Android | Действие |
|---|---|---|
| expo-apple-authentication | iOS-only, гейт есть | нет |
| expo-notifications | нужен FCM + channel + icon | WS3 |
| @react-native-google-signin | выключен на обеих (`react-native.config.js` + `expo.autolinking.exclude`) | нет |
| expo-camera | паритет, MLKit для штрихкодов | WS7 |
| expo-image-picker | паритет, Photo Picker 13+ | WS7 |
| expo-secure-store | не переживает переустановку | FAQ |
| expo-haptics | слабее, 67 fire-and-forget | нет |
| expo-blur | слабый | WS5a |
| expo-store-review | паритет, no-op в debug | нет |
| expo-video | паритет | нет |
| Share | `url` игнорируется, `message` дублирует | нет |
| expo-updates | общий runtimeVersion — каналы врозь | WS0 |
| expo-splash-screen 57.0.8 | legacy-ключ не применяется | WS0b, WS6 |
| expo-system-ui | не установлен | WS4 |
| @sentry/react-native | gradle читает env | WS4 проверка |
| amplitude | `appSetId` по умолчанию on | WS8 |
| lottie-react-native | 1.8 МБ | WS7 |
| reanimated 4 + worklets | New Arch on; `useAnimatedKeyboard` под e2e | WS5a |
| gesture-handler, screens | паритет | WS4 |
| @gorhom/bottom-sheet | не обрабатывает back | WS5b |
| react-native-view-shot | флакает в Modal | WS7 |
| modules/device-metrics | `platforms: ["apple"]` | нет |
| expo-build-properties | пишет iOS-ключи всегда | WS4 |

---

## 10. Changelog

- **2026-09-07 (ночь)** — WS5a код готов (PR `feat/android-ws5a-visual`): `BlurViewCompat` alias-паттерном, snapshot-гейт `GlassTabBar` (iOS-дерево до/после совпало), `androidShadow`/`boxShadow` для glow, `elevation` в 6 стилях, `navigationBarTranslucent` на 5 `Modal`, таб-бар на инсетах, флаги `useAnimatedKeyboard` под edge-to-edge. Jest заведён (`jest-expo`). На устройстве не прогонялось — чеклист вынесен в WS7.
- **2026-09-08** — Влиты #160–#166. Клэмп масштаба шрифта: A/B в Expo Go на iOS-симуляторе при accessibility XXXL показал, что старый `Text.defaultProps` был no-op и на iOS (заголовок логина ломался на две строки), рабочий clamp через Metro-alias (`metro.config.js` + `lib/fontScale/`) влит #166, но **по умолчанию включён только на Android** — включение на iOS видно людям с «Размером текста» >115% и это отдельное решение перед 1.0.1 (гвард в `scaledText.tsx`). Adversarial ре-ревью после мерджей: P1 — runbook `min-version` без `platform` (починен), остальное P2: jest не гоняет Metro-alias (нужен `moduleNameMapper` или тест на `resolveRequest`), `Animated.Text`/`BottomSheetTextInput` клэмпом не накрыты, `onChange` у 4 gorhom-шитов теперь только на Android, `snapshot-ios.sh` больше не глушит stderr introspect. Перед сборкой iOS 1.0.1: визуально сверить splash с TestFlight 1.0.0 и решить вопрос клэмпа на iOS.
- **2026-09-07 (вечер)** — WS0 и WS0b выполнены в ветке `feat/android-port`. Эмпирически подтверждено, что без плагина splash на SDK 57 пустой. Синк с владельцем: аккаунты Play/Firebase отложены, сначала код.
- **2026-09-07 (ред. 2)** — adversarial review, 3 ревьюера. Опровергнуто: «переписывать нечего» (B5–B8), «токена теней нет» (есть), «клавиатура — `undefined` баг» (наоборот), «staged rollout на первый релиз», «первый AAB руками», «`edgeToEdgeEnabled` готово» (deprecated), «target 35+» (36 обязателен и уже дефолт), «CI `paths: Mobile/**`» (git-корень другой), «`google-services.json` в секрет» (публичный). Добавлено: WS0b (splash-регрессия iOS), WS4a (эмулятор), WS5b (паритет взаимодействий), OTA-каналы врозь, baseline iOS-конфига, страница удаления аккаунта, ToS-гейт, `appSetId: false`, Q1 про страну аккаунта, календарь 4–5 недель.
- **2026-09-07 (ред. 1)** — документ создан по итогам двух разведок (PACE-изоляция, аудит Mobile).
