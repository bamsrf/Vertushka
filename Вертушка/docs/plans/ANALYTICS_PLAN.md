# Аналитика — tracking plan

> Статус: **ACTIVE** · Создан 2026-08-02
> Код: [Mobile/lib/analytics.ts](../../Mobile/lib/analytics.ts) · Инициализация: [Mobile/app/_layout.tsx](../../Mobile/app/_layout.tsx)
> Родитель: [APPSTORE_LAUNCH_PLAN.md §4.1](APPSTORE_LAUNCH_PLAN.md)

## Зачем документ

Без общего списка событий через месяц их будет двести, половина с опечатками
в названиях, и ни одной воронки, которую можно построить. Здесь — что мы шлём,
как называем и чего не шлём никогда.

## Состояние

| Что | Статус |
|---|---|
| Обёртка провайдер-агностик | ✅ `lib/analytics.ts` |
| Инициализация Amplitude | ✅ в `_layout.tsx` |
| Каталог событий | ✅ размечен (см. ниже) |
| **Ключ Amplitude** | ✅ заведён EAS-переменной в окружении `production` (проверено 2026-08-26) |

`initAmplitude` вызывается под `if (amplitudeApiKey)`. Если строка пустая,
провайдер не устанавливается, а `track()` молча выбрасывает событие — **без
единой ошибки в логах**. Поэтому важно понимать всю цепочку доставки ключа.

## Как ключ доезжает до приложения

```
EAS environment `production`  →  process.env.AMPLITUDE_API_KEY
        ↓
app.config.js  →  extra.amplitudeApiKey  (фолбэк: '')
        ↓
_layout.tsx  →  initAmplitude()  →  провайдер поднят
```

**Сборки (`eas build`) — работают.** Профиль `production` не объявляет поле
`environment`, но это не проблема: EAS выбирает окружение автоматически по
конфигурации, и при `distribution: "store"` подставляет ровно `production`.
Билды 16–18 собраны этим профилем, ключ в них есть.

📌 Ключ намеренно лежит **читаемой** переменной, а не secret. Client-side ключ
Amplitude всё равно уезжает внутрь бандла и публичен по своей природе —
прятать его в secret было бы имитацией безопасности.

### ⚠️ OTA-обновления — здесь ключ теряется молча

`Constants.expoConfig.extra` при обновлении берётся **из манифеста апдейта**,
а не из исходной сборки. То есть `app.config.js` вычисляется заново в момент
`eas update` — и если `AMPLITUDE_API_KEY` в этот момент не виден, в бандл
уедет пустая строка и аналитика в проде выключится **без единой ошибки**.

Сейчас это не стреляет по случайности: локально ключ подхватывается из
`Mobile/.env`, который Expo CLI грузит до вычисления конфига. Но `.env` лежит
в `.gitignore`, а у `eas update` серверные переменные подтягиваются только по
явному флагу.

**Правило: публиковать обновления только так.**

```bash
cd Mobile && npm run update:prod
```

Скрипт заведён в `Mobile/package.json` именно для этого — чтобы правило было
исполняемым, а не запоминаемым. Разворачивается в
`eas update --environment production`.

Без флага любая публикация с машины без `.env` — другой ноутбук, новый
контрибьютор, будущий CI — тихо убьёт аналитику в проде. На момент записи
автопубликации из CI нет ни в одном workflow (`backend-tests`,
`sync-roadmap`, `uptime`); если появится — флаг обязателен там же.

## Правила именования

- `snake_case`, глагол в прошедшем времени или существительное действия:
  `app_opened`, `add_to_collection`, `import_completed`
- Свойства тоже `snake_case`: `results_count`, `discogs_id`, `query_length`
- Новое событие добавляется **только** через `lib/analytics.ts` — в экранах
  не должно быть прямых `track('...')`. Иначе имена разъезжаются
- Добавил событие — добавь строку в таблицу ниже

## Чего не шлём никогда

Это не стилистика, а граница, за которой начинается новая категория сбора
данных в App Privacy и в `privacyManifests`.

- **Сырой текст поискового запроса.** Это «Search History» — отдельная
  категория в анкете ASC. Шлём `query_length` и `results_count`; для воронки
  «искал → нашёл → добавил» этого достаточно. Исправлено 2026-08-02
- **Содержимое сообщений, заметок, bio** — «Other User Content»
- **Email, имя, любые контактные данные** в свойствах событий. `identify()`
  шлёт только внутренний `user.id`
- **Точная геолокация** — не собираем вовсе
- IP и рекламные идентификаторы отключены на уровне SDK
  (`trackingOptions: { ipAddress: false, adid: false, dma: false, carrier: false }`)

> Если когда-нибудь понадобится слать что-то из этого списка — сначала
> правится анкета App Privacy в [APPSTORE_SUBMISSION_KIT.md](APPSTORE_SUBMISSION_KIT.md) §4
> и `NSPrivacyCollectedDataTypes` в `Mobile/app.json`, и только потом код.

## Каталог событий

### Жизненный цикл
| Событие | Свойства | Где |
|---|---|---|
| `app_opened` | — | `_layout.tsx`, после инициализации SDK |

> Шлётся именно после `initAmplitude`, а не при монтировании: до инициализации
> провайдер `null` и событие теряется молча. Потерянный `app_opened` — это
> заниженный знаменатель во всех воронках и сломанный retention.

### Авторизация
| Событие | Свойства | Где |
|---|---|---|
| `register` | — | `store.ts` |
| `login` | `method` (email/apple/google/discogs) | `store.ts` |
| `logout` | — | `store.ts`, плюс `reset()` провайдера |

### Наполнение коллекции
| Событие | Свойства | Где |
|---|---|---|
| `import_completed` | `imported`, `skipped`, `total` | `settings/discogs.tsx` |
| `add_to_collection` | `discogs_id` | `(tabs)/index.tsx` |
| `remove_from_collection` | `discogs_id` | — |
| `add_to_wishlist` | `discogs_id` | `(tabs)/index.tsx` |

### Сканер
| Событие | Свойства | Где |
|---|---|---|
| `scan_barcode` | `found` | `(tabs)/index.tsx` |
| `scan_cover` | `found` | `(tabs)/index.tsx` |

### Поиск и контент
| Событие | Свойства | Где |
|---|---|---|
| `search` | `query_length`, `results_count` | `(tabs)/search.tsx` |
| `view_record` | `discogs_id` | — |
| `view_artist` | `artist_id` | — |

### Социальное и магазины
| Событие | Свойства | Где |
|---|---|---|
| `follow_user` | `target_user_id` | — |
| `book_gift` | `record_id` | — |
| `view_offers` | `discogs_id`, `count` | — |
| `offer_click` | `listing_id`, `store_slug`, `price_rub`, `discogs_id` | — |

## Воронки, которые должны работать с первого дня

Ради них всё и размечалось. Собрать в Amplitude сразу после подключения ключа.

**1. Активация — главная**
```
app_opened → register → (import_completed ИЛИ add_to_collection)
```
Activation = пользователь довёл коллекцию до непустой. Импорт и ручное
добавление считать раздельно: у прошедших импорт retention должен быть выше,
и если это так — импорт надо тащить в онбординг.

**2. Сканер**
```
scan_barcode/scan_cover → found=true → add_to_collection
```
Падение на `found=false` показывает качество распознавания. Это же — сигнал,
не пора ли крутить квоты Vision (§4.3 плана).

**3. Поиск**
```
search → results_count>0 → view_record → add_to_collection
```
Много `results_count=0` при большом `query_length` — проблема поискового
индекса, а не пользователя.

**4. Retention**
D1 / D7 / D30 по `app_opened`, с разбивкой по способу активации.

## Что делать после подключения ключа

1. Прописать `extra.amplitudeApiKey` в `Mobile/app.json`
2. Собрать **production**-билд и проверить долетание (в Expo Go SDK отсутствует,
   аналитика там всегда no-op — проверять на dev-build или в TestFlight)
3. Проверить доступность Amplitude из РФ без VPN на мобильном интернете.
   Режется — переезжаем на self-hosted PostHog, см. §4.1 плана
4. Собрать 4 воронки выше
5. Обновить review notes: формулировка про аналитику уже поправлена в ките,
   но сверить перед сабмитом

## Anti-patterns

- `track('...')` напрямую из экрана в обход `lib/analytics.ts`
- Событие на каждый рендер или скролл — Amplitude не логгер
- Событие без потребителя: если под него нет вопроса, на который оно
  отвечает, — не добавлять
- PII в свойствах, см. «Чего не шлём никогда»
- `eas update` **без** `--environment production` — молча выключает аналитику
  в проде, см. раздел про OTA выше
