# App Store Submission Kit — Вертушка

> Статус: **DRAFT → заполнить в App Store Connect** · Создан 2026-07-02
> Всё, что копируется в ASC при сабмите: review notes, метаданные, App Privacy,
> age rating. Демо-аккаунт — создать руками перед сабмитом (чеклист ниже).
> Родитель: [APPSTORE_PRERELEASE_AUDIT.md](APPSTORE_PRERELEASE_AUDIT.md) (пункты A2, A4).

---

## 1. Демо-аккаунт для ревью (A2)

Создать руками в проде перед сабмитом (5–10 минут в приложении):

- [ ] Email: `review@vinyl-vertushka.ru` (завести ящик/алиас), пароль — сгенерировать, записать в ASC
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
Email: review@vinyl-vertushka.ru
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
- Contact for complaints: support@vinyl-vertushka.ru
- Report submissions are rate-limited server-side.

ACCOUNT DELETION (5.1.1(v))
Profile → "Удалить аккаунт" (Delete account). Soft-delete with a clearly
communicated 30-day restore window, then permanent deletion.

NOTES
- The app UI is in Russian (primary market: Russia/CIS).
- Sign in with Apple and Google Sign-In are both offered (Guideline 4.8).
- No tracking, no third-party analytics active; crash reports go to our
  self-hosted error tracker. App Tracking Transparency is not required.
```

## 3. Метаданные листинга (primary locale: ru)

**Название (30):** `Вертушка — коллекция винила`
**Подзаголовок (30):** `Каталог пластинок и вишлист`

**Ключевые слова (100, без пробелов после запятых):**
`винил,пластинки,коллекция,discogs,vinyl,records,вишлист,штрихкод,каталог,барахолка,музыка`

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

**Support URL:** `https://vinyl-vertushka.ru` (добавить на страницу mailto:support@vinyl-vertushka.ru)
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

## 5. Age Rating (questionnaire)

Все ответы «None/No», кроме:
- **Unrestricted Web Access:** No (наружу открываются только конкретные ссылки магазинов)
- **User-Generated Content:** приложение содержит UGC + есть модерация (report/block/EULA —
  выполнено, см. UGC_MODERATION_M2.md). С реализованной модерацией ожидаемый рейтинг: **12+**

## 6. Прочее в ASC

- [ ] Категория: **Music** (secondary: Lifestyle)
- [ ] Price: Free, все регионы (или RU/CIS + выборочно)
- [ ] App Review contact: имя, телефон, email
- [ ] Contact for UGC complaints в metadata: support@vinyl-vertushka.ru
- [ ] Скриншоты 6.9" (1320×2868) — 5–8 шт (см. аудит A6)
- [ ] `Mobile/app.json` → решить `supportsTablet` (аудит A3 — отложено по решению 2026-07-02)
