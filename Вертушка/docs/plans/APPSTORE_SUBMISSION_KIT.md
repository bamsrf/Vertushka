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

## 2. Review Notes (вставить в ASC → App Review Information → Notes)

```
DEMO ACCOUNT
Email: review@vinyl-vertushka.store
Password: <заполнить>

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

Все ответы «None/No», кроме:
- **Unrestricted Web Access:** No (наружу открываются только конкретные ссылки магазинов)
- **User-Generated Content:** приложение содержит UGC + есть модерация (report/block/EULA —
  выполнено, см. UGC_MODERATION_M2.md). С реализованной модерацией ожидаемый рейтинг: **12+**

## 6. Прочее в ASC

- [ ] Категория: **Music** (secondary: Lifestyle)
- [ ] Price: Free, все регионы (или RU/CIS + выборочно)
- [ ] App Review contact: имя, телефон, email
- [ ] Contact for UGC complaints в metadata: support@vinyl-vertushka.store
- [ ] Скриншоты 6.9" (1320×2868) — 5–8 шт (см. аудит A6)
- [ ] `Mobile/app.json` → решить `supportsTablet` (аудит A3 — отложено по решению 2026-07-02)
