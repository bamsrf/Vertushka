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

NOTES
- The app UI is in Russian (primary market: Russia/CIS).
- Sign-in options: email + password, Sign in with Apple, and Discogs OAuth.
  Sign in with Apple is offered alongside the third-party option, as required
  by Guideline 4.8.
- Analytics: product analytics (Amplitude) records anonymous in-app events.
  No advertising, no cross-app tracking, no data brokers — App Tracking
  Transparency is not required. Crash reports go to our self-hosted tracker.
```

> **Проверено в коде 2026-08-01 — две формулировки были неверны:**
> - «Google Sign-In is offered» — кнопка выключена наглухо
>   (`SocialAuthButtons.tsx`: `showGoogle = false`). Реально предлагаются
>   Apple и Discogs. Заявлять несуществующий способ входа — путать ревьюера
>   на ровном месте.
> - «No third-party analytics active» — станет ложью в тот момент, когда
>   будет прописан ключ Amplitude (§4.1 плана). Формулировка исправлена
>   заранее; если решишь релизиться без аналитики — верни прежний текст.

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

| Data type | Collected | Linked to identity | Tracking | Purpose |
|---|---|---|---|---|
| Contact Info → Email Address | Yes | Yes | No | App Functionality |
| User Content → Photos or Videos | Yes | Yes | No | App Functionality |
| User Content → Other User Content (записи, сообщения, профиль) | Yes | Yes | No | App Functionality |
| Identifiers → User ID | Yes | Yes | No | App Functionality |
| Diagnostics → Crash Data | Yes | **No** (Sentry.setUser не вызывается — проверено 2026-07-02) | No | App Functionality |

Не собираем: точную геолокацию, контакты, историю поиска вне аппки, финансовые данные,
health, browsing history, advertising data.

Соответствует `NSPrivacyCollectedDataTypes` в `Mobile/app.json` (добавлено 2026-07-02).

**Сверка с кодом 2026-08-01 (закрывает пункт B5 аудита):**
- Мобильный Sentry **не вызывает** `setUser` — проверено грепом по `Mobile/`.
  Значит Crash Data действительно не связаны с личностью на стороне
  приложения, ответ в таблице верен.
- Бэкенд вызывает `sentry_sdk.set_user({id, username, email})`
  ([auth.py](Backend/app/api/auth.py)) — но это серверные ошибки нашего
  же API в собственном трекере, и email там уже задекларирован как
  собираемый (Contact Info → Email). Новой категории сбора не возникает,
  ответы менять не нужно.
- ⚠️ Если когда-нибудь добавишь `Sentry.setUser` в мобильном коде —
  Crash Data придётся переключить в **Linked: Yes**. Пометь это на будущее.

## 4a. Content Rights (ASC → App Review Information)

Вопрос ASC: «Does your app contain, show, or access third-party content?» →
**Yes**. Заготовка ответа:

```
The app displays vinyl release metadata (artist, title, year, label, format,
catalog number) and cover images.

- Release metadata: Discogs monthly data dumps, published by Discogs under
  CC0 (public domain dedication), plus the Discogs API used under its terms.
- Cover images: Discogs and the Cover Art Archive.
- Attribution to Discogs as the data source is displayed in the app.
- Shop listings ("where to buy") link out to the shops' own pages; we display
  price and availability and send the user to the shop's site to purchase.
  No in-app purchase of physical goods (Guideline 3.1.5(a)).
```

> ⚠️ Раздел добавлен 2026-08-01 — раньше в ките его не было вовсе, а вопрос в
> ASC обязательный. Формулировка опирается на то, что дампы Discogs
> распространяются под CC0. **Это утверждение нужно подтвердить** до
> сабмита — см. §5 плана (юр. проверка ToS). Если окажется иначе, правится
> и этот ответ, и раздел «Маркет».

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
| Profanity or Crude Humor | None | Названия треков теоретически могут содержать мат, но мы его не показываем крупно и не генерируем |
| Alcohol, Tobacco, or Drug Use | None | |
| Medical or Treatment Information | None | Новый обязательный вопрос — не пропустить |
| Health or Wellness Topics | None | |
| Все виды насилия и оружия | None | |
| Gambling / Simulated Gambling / Loot Boxes | None | |
| Contests | None | ⚠️ пересмотреть при запуске конкурсных in-app events |

**Расчёт итога:** Social Media → 13+ · Sexual Content Infrequent → 13+ ·
Mature Themes Infrequent → 9+ · остальное → 4+. Максимум = **13+**.

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

## 6. Прочее в ASC

- [ ] Категория: **Music** (secondary: Lifestyle)
- [ ] Price: Free, все регионы (или RU/CIS + выборочно)
- [ ] App Review contact: имя, телефон, email
- [ ] Contact for UGC complaints в metadata: support@vinyl-vertushka.store
- [ ] Скриншоты 6.9" (1320×2868) — 5–8 шт (см. аудит A6)
- [ ] `Mobile/app.json` → решить `supportsTablet` (аудит A3 — отложено по решению 2026-07-02)
