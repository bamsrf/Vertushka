# App Store Submission Kit — Вертушка

> Статус: **DRAFT → заполнить в App Store Connect** · Создан 2026-07-02
> Всё, что копируется в ASC при сабмите: review notes, метаданные, App Privacy,
> age rating. Демо-аккаунт — создать руками перед сабмитом (чеклист ниже).
> Родитель: [APPSTORE_PRERELEASE_AUDIT.md](APPSTORE_PRERELEASE_AUDIT.md) (пункты A2, A4).

---

## 1. Демо-аккаунт для ревью (A2)

Создать руками в проде перед сабмитом (5–10 минут в приложении):

- [ ] Email: `review@vinyl-vertushka.store` (завести ящик/алиас), пароль — сгенерировать, записать в ASC
- [ ] Регистрация через email+пароль (НЕ Apple/Google — у ревьюера не будет доступа)
- [ ] Наполнить: 15–20 записей в коллекции (через поиск + пара через скан штрихкода), 5+ в вишлисте, 1–2 папки
- [ ] Публичный профиль активен (дефолт), заполнить bio
- [ ] Открыть ачивки (добавление записей само откроет несколько)
- [ ] Отправить 1–2 сообщения между демо-аккаунтом и основным (чтобы чат был не пустой)
- [ ] Проверить: логин работает, verify-code НЕ требуется для входа по паролю

⚠️ Демо-аккаунт не удалять и не банить. Email-верификация: вход по паролю не должен
требовать доступа к почте — проверить перед сабмитом.

### 1.1. Это обязательно, а не опция

Guideline 2.1 (App Completeness): если в приложении есть функции с аккаунтом,
нужно предоставить **работающий демо-аккаунт** либо полноценный demo mode.
Без этого — гарантированный реджект. По статистике Apple **больше 40%
нерешённых замечаний приходится именно на 2.1**, и самая частая причина —
ревьюер не смог войти под выданными данными.

Альтернатива в виде встроенного demo mode существует, но требует
**предварительного согласования с Apple** и оправдана только когда выдать
аккаунт мешают юридические причины. Нам не нужна.

### 1.2. Куда вписывать пароль — и куда не надо

| Место | Что туда |
|---|---|
| **App Review Information → Sign-In Information** (галочка *Sign-in required*, поля User name / Password) | ✅ **Сюда.** Это структурированное поле, ревьюер смотрит именно в него |
| App Review Information → **Notes** | Только если нужен **дополнительный код** (2FA, инвайт) или **несколько типов аккаунтов**. У нас ни того, ни другого |
| Репозиторий, `store.config.json`, любой файл в git | ❌ Никогда |

⚠️ **Не дублировать пароль в Notes и в Sign-In одновременно.** Один секрет в
двух местах рано или поздно разъедется, и ревьюер возьмёт устаревший — это
реджект по 2.1 на ровном месте. Поэтому из шаблона §2 блок `DEMO ACCOUNT`
убран.

### 1.3. Гигиена демо-аккаунта

Аккаунт настоящий и живёт в проде, поэтому обращаться с ним как с настоящим:

- **Отдельный аккаунт только для ревью.** Не личный, не админский.
- **Уникальный пароль**, нигде больше не используемый. Хранить в менеджере паролей, не в заметках и не в переписке.
- **Без привилегий:** никаких админ-эндпоинтов, доступа к чужим данным, к модерации, к платёжным методам.
- **Не удалять между релизами.** Apple логинится под ним при **каждом** обновлении, не только на первом сабмите. Мягкое удаление с 30-дневным окном тут тоже опасно — восстановить успеешь, но апдейт словит отказ.
- **Меняешь пароль — сразу обнови в ASC.** Иначе следующий апдейт отклонят.

⚠️ **Специфика Вертушки — два момента, которые легко упустить:**

1. **У демо-аккаунта публичный профиль**, и его увидят реальные пользователи: он появится в поиске по людям и в социальной ленте. Это нормально, но держать в его коллекции и bio что-то личное не стоит.
2. **В его переписке будут наши сообщения** — по чек-листу выше мы специально наполняем чат, чтобы он не был пустым. Ревьюер их прочитает. Не писать там ничего, кроме нейтральных реплик про пластинки.

⚠️ **Главный технический риск — вход.** У ревьюера нет доступа к ящику
`review@vinyl-vertushka.store`. Значит вход по паролю **не должен** требовать
кода из почты, 2FA или подтверждения устройства. Проверить это живьём
на чистом устройстве **до** сабмита — это ровно тот пункт, на котором чаще
всего валятся.

## 2. Review Notes (вставить в ASC → App Review Information → Notes)

> ⚠️ Блок `DEMO ACCOUNT` из шаблона **убран намеренно** (2026-08-17) —
> логин и пароль вписываются в поля **Sign-In Information**, а не сюда.
> Причину см. §1.2: один секрет в двух местах разъедется.

```
WHAT THE APP IS
Vertushka is a cataloging app for vinyl record collectors (Russian-speaking
market). Users scan barcodes or search to add records to their collection and
wishlist, track collection value, share a public profile, and message other
collectors.

SUGGESTED 5-MINUTE SCENARIO
1. Log in with the demo account above.
2. Collection tab — browse the demo collection, open any record card.
3. Search tab — search "Pink Floyd", open a release, add it to the collection.
4. Scan (camera icon) — barcode scanner (any vinyl/CD barcode works).
5. Profile — public profile, achievements, settings (Terms, Privacy,
   Delete account are all in-app).

DATA SOURCES / RIGHTS
- Release metadata comes from the Discogs monthly data dumps, published by
  Discogs under the CC0 (public domain) license, and from the Discogs API.
  Attribution is shown on every record card.
- Cover images: Discogs / Cover Art Archive. 
- "Buy" section links out to external vinyl shops (physical goods, opened
  in browser — no in-app purchases; Guideline 3.1.5(a)).

USER-GENERATED CONTENT (Guideline 1.2)
User-visible UGC: user-submitted records, public profiles, direct messages.
Safeguards in place:
- Report buttons on records, profiles and in chats (flag icon / "..." menu).
- Block user — in chats and on profiles.
- Zero-tolerance policy in the Terms of Use (in-app: Profile → Terms).
- Reported content is reviewed within 24 hours; content can be hidden and
  users banned via our moderation endpoints.
- Contact for complaints: support@vinyl-vertushka.store
- Report submissions are rate-limited server-side.

ACCOUNT DELETION (5.1.1(v))
Profile → "Удалить аккаунт" (Delete account). Soft-delete with a clearly
communicated 30-day restore window, then permanent deletion.
For accounts created with Sign in with Apple, deleting the account also
revokes the Apple token via the Sign in with Apple REST API
(appleid.apple.com/auth/revoke).

NOTES
- The app UI is in Russian (primary market: Russia/CIS).
- Sign-in options: email + password, Sign in with Apple, and Discogs OAuth.
  Sign in with Apple is offered alongside the third-party option, as required
  by Guideline 4.8.
- Analytics: product analytics (Amplitude) records anonymous in-app events.
  No advertising, no cross-app tracking, no data brokers — App Tracking
  Transparency is not required. Crash reports go to our self-hosted tracker.
```

> **Сверено с кодом 2026-08-18:**
> - **Способы входа — email+пароль, Apple, Discogs.** Google-вход выключен и с
>   2026-08-18 не собирается в бинарь вовсе: нативная часть исключена из
>   автолинковки (`Mobile/react-native.config.js` + `expo.autolinking.exclude`),
>   плагин убран из `app.json`. JS-код и бэкенд-эндпоинт `/auth/google` живы,
>   рубильник — `GOOGLE_SIGN_IN_ENABLED` в `SocialAuthButtons.tsx`. Заявлять
>   Google в notes нельзя, пока рубильник не вернут в `true`.
> - **Аналитика Amplitude активна** — формулировка в notes верна и должна
>   остаться. Если релизиться без ключа, абзац про аналитику убрать.
> - **Отзыв Apple-токена реализован** (`Backend/app/services/apple_auth.py`).
>   ⚠️ Работает только когда в прод-окружении заданы `APPLE_CLIENT_ID`,
>   `APPLE_TEAM_ID`, `APPLE_KEY_ID` и `APPLE_PRIVATE_KEY` (содержимое .p8).
>   Без ключа код молча деградирует в no-op — то есть в notes будет написано
>   про отзыв, а отзыва не будет. **Проверить перед сабмитом.**

## 3. Метаданные листинга (primary locale: ru)

> ⚠️ **Раздел устарел как источник правды (2026-08-14).** Метаданные листинга теперь
> ведутся в [APPSTORE_ASO_KIT.md §5](APPSTORE_ASO_KIT.md#5-форма-метаданные-app-store-connect) —
> там варианты названия/подзаголовка с обоснованием, семантическое ядро, кросс-локализация
> (ru + en-GB даёт ×2 к ключевым словам на RU-сторфронте) и структура описания.
> Черновики ниже сохранены как исходная точка; **перед сабмитом заполнять ASO Kit и
> копировать в ASC оттуда.**

**Название (30):** `Вертушка — коллекция винила`
**Подзаголовок (30):** `Каталог пластинок и вишлист`

**Ключевые слова (100, без пробелов после запятых):**
`винил,пластинки,коллекция,vinyl,records,вишлист,штрихкод,каталог,барахолка,музыка,меломан`

> ⚠️ **`discogs` из ключевых слов убран (2026-08-01).** Чужой товарный знак в
> метаданных — основание для реджекта и для претензии правообладателя. В
> описании упоминание источника данных остаётся: это добросовестная
> атрибуция, а не попытка ранжироваться по чужому бренду. То же правило для
> названия и подзаголовка.

**Описание (RU):**
```
Вертушка — приложение для коллекционеров виниловых пластинок.

• Сканируй штрихкод — пластинка находится мгновенно
• Веди коллекцию: форматы, года, лейблы, стоимость
• Вишлист с папками — делись им с друзьями, чтобы получать правильные подарки
• Публичный профиль: покажи полку друзьям, следи за коллекциями других
• Ачивки за пополнение коллекции
• «Где купить» — цены на пластинку в магазинах
• Сообщения: обсуждай релизы с другими коллекционерами

Данные о релизах — Discogs. Приложение бесплатное.
```

**Описание (EN, доп. локаль — опционально):**
```
Vertushka is an app for vinyl record collectors.

• Scan a barcode — the record is found instantly
• Track your collection: formats, years, labels, value
• Wishlist with folders — share it so friends gift you the right records
• Public profile: show off your shelf, follow other collectors
• Achievements for growing your collection
• "Where to buy" — prices from record shops
• Messages: discuss releases with fellow collectors

Release data by Discogs. The app is free.
```

> **Домен-конвенция:** сайт/страницы/API — на `.ru`; почтовый ящик — на `.store`.
> Support/complaint email = `support@vinyl-vertushka.store`, все URL = `vinyl-vertushka.ru`.

**Support URL:** `https://vinyl-vertushka.ru` (добавить на страницу mailto:support@vinyl-vertushka.store)
**Marketing URL (опц.):** `https://vinyl-vertushka.ru`
**Privacy Policy URL:** `https://vinyl-vertushka.ru/privacy`
**Copyright:** `© 2026 Вертушка`

## 4. App Privacy (questionnaire) — ответы

Data collection: **Yes**. Tracking: **No** (ATT не нужен).

> ⚠️ **Пересобрано 2026-08-18 по факту кода.** Прежняя таблица (5 типов, Crash Data
> «не связаны с личностью», аналитики нет) описывала состояние до включения
> Amplitude и до `Sentry.setUser`. Ответы ниже **дословно соответствуют**
> `NSPrivacyCollectedDataTypes` в [Mobile/app.json](../../Mobile/app.json) — это
> и есть смысл раздела: анкета в ASC и манифест внутри бинаря обязаны совпадать,
> расхождение Apple ловит и заворачивает.

| Раздел ASC | Data type | Linked to identity | Tracking | Purpose |
|---|---|---|---|---|
| Contact Info | Name | Yes | No | App Functionality |
| Contact Info | Email Address | Yes | No | App Functionality |
| User Content | Photos or Videos | Yes | No | App Functionality |
| User Content | Emails or Text Messages (личные сообщения) | Yes | No | App Functionality |
| User Content | Other User Content (записи, профиль) | Yes | No | App Functionality |
| Identifiers | User ID | Yes | No | App Functionality |
| Identifiers | Device ID | Yes | No | **Analytics** |
| Usage Data | Product Interaction | Yes | No | **Analytics** |
| Diagnostics | Crash Data | **Yes** | No | App Functionality |
| Diagnostics | Performance Data | Yes | No | App Functionality |

Не собираем: точную геолокацию, контакты, историю поиска вне аппки, финансовые данные,
health, browsing history, advertising data.

**Почему именно так — сверка с кодом 2026-08-18:**
- **Analytics-цель у Device ID и Product Interaction** появилась потому, что
  Amplitude реально включён: [lib/analytics.ts](../../Mobile/lib/analytics.ts),
  ключ приходит через [app.config.js](../../Mobile/app.config.js). Пока ключа не
  было, аналитики в декларации справедливо не было — теперь есть.
- **Tracking всё равно No.** В инициализации Amplitude выключены `ipAddress`,
  `adid`, `dma`, `carrier`, регион EU, рекламных сетей и брокеров нет. Это
  продуктовая аналитика внутри приложения, а не трекинг между приложениями,
  поэтому ATT-промпт не нужен, `NSPrivacyTracking: false` верен.
- **Crash Data теперь Linked: Yes.** [_layout.tsx](../../Mobile/app/_layout.tsx)
  вызывает `Sentry.setUser({ id })` — крэши связаны с идентификатором. Старая
  формулировка «setUser не вызывается» устарела и была бы прямой ложью в анкете.
- **Бэкенд шлёт в Sentry `{id, username}` без email** ([auth.py](../../Backend/app/api/auth.py))
  — раньше в этом разделе было написано, что уходит и email. Не уходит.
- Из поиска в аналитику уходит только длина запроса и число результатов, сам
  текст остаётся на устройстве — поэтому Search History не декларируется.

## 4a. Content Rights (ASC → App Review Information)

Вопрос ASC: «Does your app contain, show, or access third-party content?» →
**Yes**. Заготовка ответа:

**Ответ в диалоге:** «Yes, it contains, shows, or accesses third-party
content, and I have the necessary rights». Вариант «No» был бы прямой
неправдой — мы показываем чужие метаданные и обложки.

```
The app displays vinyl release metadata (artist, title, year, label, format,
catalog number) and cover artwork.

- Release metadata: Discogs monthly data dumps, released under CC0 (public
  domain dedication), plus the Discogs API used under its terms.
- Cover artwork is shown for identification of a specific pressing, sourced
  from Discogs and the Cover Art Archive. Artwork remains the property of its
  respective rights holders; we display it solely to identify the release a
  user is cataloguing or looking for.
- Attribution to Discogs as the data source is displayed in the app.
- Shop listings ("where to buy") link out to the shops' own pages; we display
  price and availability and send the user to the shop's site to purchase.
  No in-app purchase of physical goods (Guideline 3.1.5(a)).
```

### 4a.1. Проверено 2026-08-18 — и одна поправка

**CC0 на метаданные подтвердился.** Discogs распространяет месячные дампы
(Release, Artist, Label, Master) под CC0 No Rights Reserved. Пункт §5 плана
про юридическую проверку ToS в этой части закрыт.

⚠️ **Но CC0 не распространяется на изображения, и раньше здесь это
смешивалось в один пункт.** Discogs прямо оговаривает: дискографические
данные — общественное достояние, **изображения — нет**; они лежат на их
серверах по принципам fair use, и массовое перераспространение в лицензию
не входит.

Что это значит для нас:

| | Статус |
|---|---|
| Метаданные релизов | ✅ CC0, вопросов нет |
| Показ обложки для идентификации пресса | практика всей отрасли (Discogs, MusicBrainz, магазины); формулировка выше описывает именно это |
| **Зеркалирование обложек в свой S3** ([COVERS_S3_IMGPROXY_MILESTONE.md](COVERS_S3_IMGPROXY_MILESTONE.md)) | ⚠️ **это уже не показ, а хранение и раздача копий** — то, что Discogs называет mass re-distribution |

📌 **Для App Review это не блокер.** Apple задаёт вопрос-галочку, а не
проводит аудит прав, и ответ «Yes, I have the necessary rights» — стандартный
для любого каталога. Риск здесь не со стороны Apple, а со стороны Discogs
(их ToS) и правообладателей обложек.

⚠️ **Оценить этот риск я не могу — это вопрос к юристу, а не к разработке.**
Что можно сказать по фактам: копии обложек у нас лежат на своём хранилище,
формально это выходит за рамки того, что Discogs разрешает дампами. Стоит
хотя бы понимать, что это осознанное решение, а не недосмотр.

## 5. Age Rating (questionnaire)

> ⚠️ **Переписано 2026-08-17.** Раньше здесь стояло «ожидаемый рейтинг **12+**».
> **Такого рейтинга больше не существует** — Apple заменил шкалу в 2025 году.

### 5.1. Что изменилось у Apple

| Было | Стало |
|---|---|
| 4+ · 9+ · **12+** · **17+** | 4+ · 9+ · **13+** · **16+** · **18+** |

12+ и 17+ упразднены, добавлены 13+, 16+, 18+. Анкету переписали: появились
обязательные вопросы про **in-app controls**, **capabilities** (соцфункции,
чат, лента), **медицинские/wellness темы** и **насилие**. Все существующие
приложения Apple переоценил автоматически по старым ответам.

⚠️ **Дедлайн ответа на новую анкету — 31 января 2026, он уже прошёл.** Пока
новые вопросы не отвечены, App Store Connect **не даст отправить сборку**.
Это не «сделать перед сабмитом», это «сделать до того, как жать Submit» —
проверить в ASC → App Information прямо сейчас, до сборки.

⚠️ **Второй дедлайн, отдельный от первого.** Вопросы именно про **social media**
Apple добавила в анкету 09.07.2026, и **с сентября 2026 ответы на них обязательны**
при сабмите новых приложений и апдейтов. Наш первый сабмит попадает в это окно:
поле не «желательно заполнить», без него не отправить. Побочные следствия ответа
`Present` — дескриптор **Social Media** на продуктовой странице и попадание в
категорию Time Allowance «Social Media» в iOS 27+.

### 5.2. Как устроена анкета — полная карта

Анкета идёт в два блока. **Важно понять принцип: итоговый рейтинг — это
максимум по всем ответам.** Не сумма, не среднее. Один ответ «Frequent» в
одной строке перебивает все остальные «None».

#### Блок 1. In-App Controls & Capabilities (новый в 2025)

Здесь отмечаются возможности приложения, а не контент.

| Вопрос | Значения | Куда тянет |
|---|---|---|
| Parental Controls | None / Present | не поднимает |
| Age Assurance | None / Present | не поднимает |
| **Unrestricted Web Access** | None / Present | **16+** ⚠️ |
| User-Generated Content | None / Present | не поднимает сам по себе |
| **Social Media** | None / Present | **13+** |
| Social Media Disabled for Users Under 13 | None / Present | 13+ (в Австралии 16+) |
| Messaging and Chat | None / Present | не поднимает сам по себе |
| Advertising | None / Present | не поднимает |

⚠️ Контринтуитивно: **чат и UGC сами по себе рейтинг не поднимают** — поднимает
именно флаг **Social Media**. Apple определяет его как возможность
распространять, усиливать или взаимодействовать с пользовательским контентом
через ленту или похожий механизм обнаружения.

#### Блок 2. Content Descriptors

| Дескриптор | Значения | Infrequent → | Frequent → |
|---|---|---|---|
| Profanity or Crude Humor | None / Infrequent / Frequent | 9+ | 13+ |
| Horror/Fear Themes | None / Infrequent / Frequent | 9+ | 13+ |
| Alcohol, Tobacco, or Drug Use | None / Infrequent / Frequent | 13+ | **18+** |
| Medical or Treatment Information | None / Infrequent / Frequent | 13+ | 16+ |
| Health or Wellness Topics | None / Present | 9+ | — |
| Mature or Suggestive Themes | None / Infrequent / Frequent | 9+ | 16+ |
| **Sexual Content or Nudity** | None / Infrequent / Frequent | **13+** | **18+** |
| Graphic Sexual Content and Nudity | None / Infrequent / Frequent | **Unrated — в App Store не публикуется** | |
| Cartoon or Fantasy Violence | None / Infrequent / Frequent | 9+ | 13+ |
| Realistic Violence | None / Infrequent / Frequent | 13+ | **18+** |
| Prolonged Graphic or Sadistic Realistic Violence | — | **Unrated — не публикуется** | |
| Guns or Other Weapons | None / Infrequent / Frequent | 9+ | 13+ |

#### Блок 3. Chance-Based Activities

| Дескриптор | Значения | Куда тянет |
|---|---|---|
| Gambling | None / Present | **18+** |
| Simulated Gambling | None / Infrequent / Frequent | 13+ → 18+ |
| Contests | None / Infrequent / Frequent | 4+ → 13+ |
| Loot Boxes | None / Present | 9+ (в Австралии 16+) |

⚠️ **Contests** — не проскочить мимо. Если когда-нибудь запустим конкурс или
розыгрыш через in-app event (ASO Kit §12), эту строку придётся менять.

### 5.3. Ответы для Вертушки

| Вопрос | Ответ | Почему |
|---|---|---|
| **Social Media** | **Present** | Лента активности, подписки, публичные профили. Это и есть наш пол — **13+** |
| Messaging and Chat | Present | TG-style DM. Рейтинг не двигает, но скрывать нельзя |
| User-Generated Content | Present | Свои пластинки, профили, сообщения |
| Parental Controls | None | Нет |
| **Unrestricted Web Access** | **None** | ⚠️ **Самый дорогой ответ в анкете.** Наружу открываются только конкретные ссылки магазинов. Ответить Present — сразу 16+ на ровном месте |
| Advertising | None | Рекламы нет |
| **Sexual Content or Nudity** | **Infrequent** | Обложки пластинок — см. §5.4 |
| **Mature or Suggestive Themes** | **Infrequent** | Там же |
| **Profanity or Crude Humor** | **Infrequent** | Названия треков и альбомов приходят из Discogs, мат в них встречается. Infrequent → 9+, ниже нашего пола — **стоит ноль** |
| **Horror/Fear Themes** | **Infrequent** | Обложки метала бывают откровенно хоррорными. Infrequent → 9+ — **стоит ноль** |
| **Alcohol, Tobacco, or Drug Use** | **Infrequent** | Отсылки к веществам в названиях и на обложках — обычное дело. Infrequent → 13+, ровно наш пол — **стоит ноль**. ⚠️ **Frequent здесь = 18+**, не перепутать |
| Medical or Treatment Information | None | Новый обязательный вопрос — не пропустить |
| Health or Wellness Topics | None | |
| Все виды насилия и оружия | None | |
| Gambling / Simulated Gambling / Loot Boxes | None | |
| Contests | None | ⚠️ пересмотреть при запуске конкурсных in-app events |

**Расчёт итога:** Social Media → 13+ · Sexual Content Infrequent → 13+ ·
Alcohol Infrequent → 13+ · Mature Themes / Profanity / Horror Infrequent → 9+ ·
остальное → 4+. Максимум = **13+**.

> ⚠️ **Пересмотрено 2026-08-18.** Раньше по Profanity, Horror и Alcohol стояло
> `None`. Заменено на `Infrequent` — принцип тот же, что и с обложками (§5.4):
> **пока ответ не поднимает итог выше 13+, декларировать безопаснее, чем
> умалчивать.** Мы показываем чужие названия и обложки, которые не
> контролируем; `None` означало бы, что такого контента в приложении нет
> вовсе, а это неправда.
>
> **Единственная строка, где ошибка дорогая, — Alcohol.** `Infrequent` = 13+,
> `Frequent` = **18+**. Разница между «встречается» и «встречается регулярно»
> здесь стоит пяти лет рейтинга.
>
> 📌 Цена решения: дескрипторы **видны на странице приложения** под
> возрастным рейтингом. То есть на витрине появится строчка вроде
> «Infrequent/Mild Alcohol, Tobacco, or Drug Use or References». Само число
> 13+ не меняется. Если это смущает — можно оставить `None`, но тогда демо-
> коллекция (§1) должна быть заведомо чистой, иначе ревьюер найдёт
> расхождение сам.

### 5.4. Обложки альбомов — и почему декларировать их бесплатно

Мы показываем обложки из Discogs и Cover Art Archive. Среди них есть
откровенные: ню и провокационная графика встречаются в роке, метале и джазе
постоянно — это часть истории оформления пластинок. Формально чужой контент,
но показываем его мы, в своём интерфейсе.

> ⚠️ **Поправка от 2026-08-17.** В первой версии этого раздела было сказано,
> что декларация «может поднять рейтинг до 16+». **Это неверно.** По
> официальной таблице Apple `Sexual Content or Nudity — Infrequent` даёт
> **13+**, а не 16+. До 18+ тянет только `Frequent`.

**А 13+ у нас уже есть от флага Social Media.** Значит декларация обложек
**не меняет рейтинг вообще** — она бесплатна.

| Вариант | Итоговый рейтинг | Риск |
|---|---|---|
| **A. Задекларировать Infrequent** ✅ | **13+** — без изменений | Никакого |
| B. Оставить None | 13+ | Ревьюер листает демо-коллекцию, видит ню на обложке → несоответствие рейтинга, реджект и переоценка задним числом |

▸ **РЕШЕНИЕ: вариант A** — декларируем `Sexual Content or Nudity: Infrequent`
и `Mature or Suggestive Themes: Infrequent`. Рейтинг остаётся 13+.
Дата: 2026-08-17.

⚠️ Не ставить `Frequent`: это 18+ и оно неправдиво — приложение не про такой
контент, обложки появляются эпизодически и не являются его темой.

⚠️ Технической фильтрации обложек нет и в 1.0 не будет: Discogs не отдаёт
NSFW-флаг, свой классификатор — отдельная задача.

### 5.4a. Итог анкеты — факт, 2026-08-18

Анкета пройдена. **Calculated Rating: 13+** — ровно то, что считали в §5.3.
Переключатель *Age Categories and Override* оставлен в **Not Applicable**
(решение из §5.5). *Age Suitability URL* — пусто, он опциональный и нам
нечего туда положить.

⚠️ **Побочный эффект, которого я не предсказал.** На последнем шаге ASC
показал:

> Due to local laws, this app will not be sold in the following countries
> or regions: **Afghanistan, Morocco**

Это следствие декларации `Sexual Content or Nudity: Infrequent` (и, возможно,
`Mature or Suggestive Themes`): в этих двух странах местные законы не
допускают приложения с такими дескрипторами, и Apple исключает их
автоматически.

**То есть декларация обложек стоила не совсем ноль** — два сторфронта, а не
нисколько, как утверждалось в §5.4. Цена всё равно принимается: Афганистан и
Марокко к нашей аудитории отношения не имеют, а альтернатива — расхождение
между заявленным рейтингом и тем, что ревьюер увидит на обложках.

📌 Если когда-нибудь эти рынки станут нужны — единственный способ вернуть их
это убрать дескриптор, то есть либо фильтровать обложки технически, либо
заявить `None` и жить с риском.

### 5.5. Ставить ли 16+ вручную — отдельное решение

Apple разрешает вручную поднять рейтинг выше расчётного (понизить — нет).
Обсуждалось поставить **16+** добровольно.

**Единственный настоящий аргумент за:** в приложении есть личные сообщения с
медиа и публичные профили, то есть тринадцатилетний может переписываться со
взрослыми незнакомцами. Это осознанная политика безопасности, и такой выбор
защитим.

**Аргументы против:**
- рейтинг режет охват — родительский контроль, фильтры, часть редакционных подборок;
- наша аудитория 25–45 (ASO Kit §2.4), «защита» здесь скорее номинальная;
- модерация уже есть: report, block, EULA, разбор жалоб ≤24ч
  ([UGC_MODERATION_M2.md](UGC_MODERATION_M2.md)) — то, ради чего обычно и
  поднимают рейтинг, у нас закрыто механикой.

📌 **Рекомендация: оставить 13+.** 16+ не даёт ничего, чего не даёт модерация,
но стоит охвата. Если решишь иначе — это законное продуктовое решение, просто
запиши здесь причину, чтобы через полгода не гадать.

▸ **РЕШЕНИЕ:** `13+ (расчётное)` / `16+ вручную, причина: _____` → `_____`

### 5.6. Практическое правило

**Не завышать рейтинг «на всякий случай».** Он режет охват: родительский
контроль, фильтры в поиске, часть редакционных подборок. Ставить выше, чем
насчитала анкета, имеет смысл только если этого требует собственная политика
продукта.

### 5.7. Держать согласованным с Terms

В [terms.tsx](../../Mobile/app/legal/terms.tsx) и на `/terms` записано «не младше
13 лет, до 18 — с согласия родителя»: строка добавлена вместе с этим разделом,
раньше минимального возраста в условиях не было вовсе. Если по §5.5 решишь
поднять рейтинг до 16+, эту строку надо поднять следом — иначе документы
противоречат витрине, а это ровно тот тип расхождения, который ревьюер замечает.

## 6. Прочее в ASC

- [ ] Категория: **Music** (secondary: Lifestyle)
- [ ] Price: Free
- [ ] Availability (география) — решение в [ASO Kit §1.4](APPSTORE_ASO_KIT.md); см. блок про trader status ниже
- [ ] App Review contact: имя, телефон, email
- [ ] Contact for UGC complaints в metadata: support@vinyl-vertushka.store
- [ ] Скриншоты 6.9" (1320×2868) — 5–8 шт (см. аудит A6)
- [x] `Mobile/app.json` → `supportsTablet: false` (решение 2026-07-02, в коде подтверждено)

## 7. Trader status (DSA) — заполняется до сабмита

С февраля 2025 Apple требует декларировать trader status **у всех** аккаунтов,
независимо от географии распространения. Для приложений, доступных в ЕС,
контактные данные трейдера (адрес, телефон, email) **публикуются на витрине**
и должны быть верифицированы; без этого Apple снимает приложение со всех 27
сторфронтов ЕС — автоматически, даже если оно уже опубликовано и ничего в нём
не менялось.

**Наш случай:** публикуемся через аккаунт разработчика в **Бразилии**
(подтверждён, подписка оплачена на год). Значит:

> ⚠️ **Исправлено 2026-08-18 по документации Apple.** Раньше здесь было
> написано, что ради непубликации адреса нужно исключать ЕС из Availability.
> **Это неверно и вело к дорогой ошибке** — см. §7.1.

- [ ] Декларацию заполняет владелец аккаунта — данными бразильского
      юрлица/физлица, не российскими. Наши данные тут не подходят вообще.
- [ ] Выбрать статус **по факту**, а не по удобству (§7.1)
- [ ] Если выбран **trader** — проверить, что верификация пройдена **до**
      отправки билда: она занимает дни, а не минуты. У **non-trader**
      верификации нет вообще.

### 7.1. Trader или non-trader — и почему ЕС исключать не надо

Ключевое, что меняет картину: **статус non-trader НЕ убирает приложение из
ЕС и не требует публиковать вообще никаких контактов.**

| | Trader | Non-trader |
|---|---|---|
| Приложение доступно в ЕС | да | **да** |
| Публикуются адрес/телефон/email | **да, на странице приложения** | **нет** |
| Верификация Apple | да, занимает дни | **нет** |
| Что видит покупатель в ЕС | контакты продавца | уведомление, что потребительские права ЕС к сделке не применяются |

**Кто такой trader** (по критериям Apple): есть выручка — IAP, платное
приложение, реклама; коммерческое продвижение; регистрация по НДС; разработка
в рамках бизнеса или профессии. **Не trader** — хобби без намерения
коммерциализации.

**Для Вертушки 1.0** приложение бесплатное, без IAP и без рекламы, поэтому
**non-trader выглядит честным ответом**. Тогда: ЕС остаётся доступен, ничего
не публикуется, ждать верификацию не нужно.

⚠️ **Но это временно.** Как только заработают аффилиатные переходы в магазины
(M7, [PLAN_MONETIZATION.md](PLAN_MONETIZATION.md)) — появляется выручка, и
статус придётся менять на trader вместе с публикацией контактов. Заложить это
в план M7, а не обнаружить постфактум.

⚠️ **Исключать ЕС из Availability — плохая идея**, и не из-за европейцев.
Сторфронт определяется страной Apple ID, а не местом жительства. Немалая
часть русскоязычной аудитории после отключения платежей Apple в РФ перевела
Apple ID в другие страны — и часть из них европейские (Германия, Польша,
Прибалтика, Кипр, Нидерланды). Исключив ЕС, мы делаем приложение **невидимым
для собственной целевой аудитории**, которая живёт в России и говорит
по-русски. Популярные не-европейские варианты (Казахстан, Армения, Грузия,
Турция, Сербия, ОАЭ) при этом не пострадали бы — но резать нужно только то,
что действительно мешает, а здесь не мешает ничего.

### 7.2. Где заполняется

| Уровень | Путь в ASC |
|---|---|
| Аккаунт | **Business** → вкладка *Agreements* → секция *Compliance* → **Digital Services Act** → *Complete Compliance Requirements* |
| Приложение | **Apps** → Вертушка → **App Information** → секция *App Store Regulations and Permits* → **Digital Services Act** → *Edit* |

Если trader и владелец — юрлицо, адрес подтягивается из D-U-N-S, руками нужны
телефон и email. Если физлицо — адрес (допустим P.O. Box), телефон, email.
Телефон и email подтверждаются кодом.

## 8. Ключ Sign in with Apple (.p8) — блокер отзыва токена

Отзыв токена при удалении аккаунта (Guideline 5.1.1(v)) реализован в
`Backend/app/services/apple_auth.py`, но включается только при заполненном
окружении:

> ⚠️ **Проверено на проде 2026-08-18 — ключ НЕ настроен.** В окружении
> контейнера заполнен только `APPLE_CLIENT_ID` (17 символов — это
> `com.vertushka.app`). `APPLE_TEAM_ID`, `APPLE_KEY_ID` и `APPLE_PRIVATE_KEY`
> отсутствуют вовсе.
>
> `is_configured()` требует **все четыре** значения, поэтому возвращает `False`,
> и `revoke_refresh_token()` молча ничего не делает. При этом в review notes
> (§2) написано, что отзыв токена работает. Это расхождение между заявленным
> и фактическим — ровно то, что проверяют по 5.1.1(v).
>
> Как убедиться, что починилось: удалить тестовый аккаунт, вошедший через
> Apple, и найти в логах `apple_token_revoke ... revoked=True`.

- [ ] В developer.apple.com → Keys создать ключ с включённым **Sign in with Apple**
      (делает владелец бразильского аккаунта), скачать `.p8` — он выдаётся **один раз**
- [ ] Прописать в прод-окружении: `APPLE_CLIENT_ID` (= `com.vertushka.app`),
      `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (содержимое .p8,
      переносы можно экранировать как `\n`)
- [ ] Проверить на живом проде: вход через Apple → удаление аккаунта → в логах
      `apple_token_revoke ... revoked=True`. Пока ключа нет, код тихо ничего не
      делает — а в review notes уже написано, что отзыв есть.
