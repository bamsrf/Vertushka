# План: первый билд Вертушки в TestFlight

> Цель — собрать iOS-билд и раздать его внутренним тестерам в TestFlight. Это **не** публичный релиз в App Store (маскот M1, скриншоты и полные метаданные тут не нужны — они для публичного submit).
>
> Контекст: код почти готов (Фазы 0/3/4 из [PLAN_RELEASE_v2.md](PLAN_RELEASE_v2.md) фактически закрыты). Apple Developer Program оплачен, доступ к App Store Connect есть. Xcode не требуется — сборка идёт в облаке EAS Build.

---

## Предпосылки (проверить один раз)

- [ ] Node установлен (`node -v`)
- [ ] `eas-cli` установлен глобально: `npm i -g eas-cli`
- [ ] Залогинен в Expo: `eas login` → `eas whoami` показывает аккаунт `bamsrf`
- [ ] Apple ID с доступом к App Store Connect под рукой (логин + пароль; 2FA включён)

---

## Шаг 1 — Создать app-запись в App Store Connect

Без этой записи `eas submit` не знает, куда лить билд.

1. Зайти на [appstoreconnect.apple.com](https://appstoreconnect.apple.com) → **My Apps** → **+** → **New App**
2. Заполнить:
   - **Platform:** iOS
   - **Name:** Вертушка (имя в сторе; можно менять позже)
   - **Primary Language:** Russian
   - **Bundle ID:** выбрать `com.vertushka.app` (должен уже существовать в Developer-аккаунте; если нет — создать на [developer.apple.com](https://developer.apple.com/account/resources/identifiers) → Identifiers → App IDs)
   - **SKU:** любой уникальный строковый ID, напр. `vertushka-ios-001`
3. Создать. Запомнить два значения:
   - **`ascAppId`** — числовой App ID из URL записи (`.../app/`**`1234567890`**`/...`) или в App Information → General → Apple ID
   - **`appleTeamId`** — 10-символьный Team ID: [developer.apple.com/account](https://developer.apple.com/account) → Membership details

**Результат шага:** на руках `ascAppId` (числовой) + `appleTeamId` (10 символов).

---

## Шаг 2 — Вписать значения в `eas.json`

Файл: `Mobile/eas.json`, блок `submit.production.ios`. Сейчас там плейсхолдеры:

```json
"submit": {
  "production": {
    "ios": {
      "ascAppId": "REPLACE_WITH_APP_STORE_CONNECT_APP_ID",
      "appleTeamId": "REPLACE_WITH_APPLE_TEAM_ID"
    }
  }
}
```

Заменить на реальные значения из Шага 1.

**Результат шага:** `eas.json` без плейсхолдеров.

---

## Шаг 3 — Заполнить Sentry DSN (рекомендуется, не блокер)

Без DSN крэши тестеров невидимы. Файл `Mobile/app.json`, поле `expo.extra.sentryDsn` (сейчас `""`).

1. [sentry.io](https://sentry.io) → создать проект типа **React Native** (если ещё нет)
2. Скопировать DSN проекта
3. Вписать в `app.json` → `extra.sentryDsn`

Можно пропустить и залить билд без Sentry, но тогда отладка крэшей вслепую.

**Результат шага:** `sentryDsn` заполнен.

---

## Шаг 4 — Проверка перед билдом (sanity check)

- [ ] `Mobile/app.json` → `version` = `1.0.0`, `bundleIdentifier` = `com.vertushka.app`
- [ ] `Mobile/lib/api.ts` → prod-ветка указывает на `https://api.vinyl-vertushka.ru/api`
- [ ] `curl https://api.vinyl-vertushka.ru/health` → `200 OK` (бэкенд жив)
- [ ] Кнопка Google Sign In скрыта в UI (эндпоинт = 501) — уже скрыта
- [ ] Зависимости свежие: `cd Mobile && npm install`

**Результат шага:** всё зелёное, можно собирать.

---

## Шаг 5 — Собрать iOS-билд в облаке

```bash
cd Mobile
eas build --platform ios --profile production
```

Что произойдёт:
1. EAS спросит Apple-креды (первый раз) → залогиниться Apple ID
2. EAS сам сгенерит Distribution Certificate + Provisioning Profile (Xcode не нужен)
3. Сборка идёт ~15–30 мин на серверах Expo
4. По завершении — ссылка на `.ipa` в EAS dashboard

**Если сборка падает** — читать лог в выводе/на expo.dev, чаще всего: версия зависимостей, отсутствует нативный конфиг. Чинить точечно.

**Результат шага:** готовый `.ipa` в EAS.

---

## Шаг 6 — Залить билд в TestFlight

```bash
eas submit --platform ios --profile production --latest
```

`--latest` берёт последний собранный билд. EAS загрузит `.ipa` в App Store Connect (тоже в облаке, без Transporter/Xcode).

После загрузки в App Store Connect → **TestFlight**:
- Билд появится со статусом **Processing** (~5–15 мин)
- Затем потребует ответ на **Export Compliance** — у нас `ITSAppUsesNonExemptEncryption: false` в app.json, поэтому вопрос проходит автоматически без ручного ввода

**Результат шага:** билд в TestFlight, статус **Ready to Test**.

---

## Шаг 7 — Раздать внутренним тестерам

В App Store Connect → **TestFlight** → **Internal Testing**:

1. Создать internal-группу (или использовать дефолтную)
2. Добавить тестеров по email (они должны быть в команде App Store Connect — до 100 internal-тестеров, **без beta-ревью**)
3. Тестеры ставят приложение **TestFlight** из App Store → принимают инвайт → ставят билд

> External-тестеры (публичная ссылка, до 10 000) требуют beta-ревью Apple — пока не нужно, начинаем с internal.

**Заполнить минимум для TestFlight** (App Store Connect → TestFlight → Test Information):
- [ ] What to Test — что тестировать (краткий сценарий на русском)
- [ ] Тестовый аккаунт (email+пароль) для входа без регистрации

**Результат шага:** билд на устройствах тестеров, фидбек идёт.

---

## Сводка значений, которые надо добыть

| Значение | Где взять | Куда вписать |
|---|---|---|
| `ascAppId` (числовой) | App Store Connect → App Information | `Mobile/eas.json` |
| `appleTeamId` (10 симв.) | developer.apple.com → Membership | `Mobile/eas.json` |
| Sentry DSN | sentry.io → React Native project | `Mobile/app.json` → `extra.sentryDsn` |

---

## Чего НЕ делаем сейчас (откладываем до публичного App Store submit)

- Маскот (M1), иконка v2, splash с маскотом
- Скриншоты iPhone 6.7"/6.5"
- Полные метаданные стора (описание, keywords, age rating, privacy nutrition labels)
- Backend Фаза 2 (multi-worker, circuit breaker, Nginx cache) — про 1000 DAU, для горстки тестеров не критично

Эти пункты живут в [PLAN_RELEASE_v2.md](PLAN_RELEASE_v2.md) Фаза 5 и блоке M2 в [ROADMAP.md](../../../ROADMAP.md).

---

## TL;DR порядок команд

```bash
npm i -g eas-cli
eas login
cd Mobile
# 1. вписать ascAppId+appleTeamId в eas.json, sentryDsn в app.json
npm install
eas build --platform ios --profile production
eas submit --platform ios --profile production --latest
# затем App Store Connect → TestFlight → Internal Testing → добавить тестеров
```
