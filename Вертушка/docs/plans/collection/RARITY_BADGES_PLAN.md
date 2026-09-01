# План: подсветка редкости пластинок

> **Статус: задеплоено и работает.** Документ актуализирован после нескольких
> итераций. Финальное состояние — четыре тира: **Канон, Коллекционка, Лимитка,
> Популярно**. Тир «1-й пресс» был открыт, потом закрыт (см. ниже почему).

---

## Context

Дать пользователю объективные сигналы редкости его пластинок: что коллекционка,
что популярная сейчас, что официальная «эталонная» версия. Все сигналы строятся
поверх данных Discogs API без ручной разметки.

---

## Финальные четыре тира

### 🩶 Канон (`is_canon`)
**Что значит:** Discogs editorial pick — версия мастер-релиза, помеченная сообществом
как `main_release`. Это «лицо альбома по версии Discogs», не обязательно
оригинальный первопресс.

**Логика:**
```python
is_canon = release.id == master.main_release_id
```
Один доп. кэшируемый запрос к `/masters/{id}` на релиз.

**Визуал (Mobile):** slate-графит палитра `#8B95A8 → #5A6B7D → #2E3844`.
`CanonBorderGlow` — двухслойная анимированная рамка (внешний glow + inset border),
5s pulse. Без вращения — «editorial pick» feeling.

**Реальные числа на тестовой коллекции (188 записей):** 22 (12%).

---

### 💚 Коллекционка (`is_collectible`)
**Что значит:** объективная редкость по рынку. Дорогая + дефицит на маркете +
не массовая. Самый сильный сигнал «реально редкая ценная пластинка».

**Логика:**
```python
is_collectible = (
    (median_price OR lowest_price) >= $100   # дорогая, fallback на lowest
    AND num_for_sale <= 3                     # ≤3 копии на маркете
    AND community.have <= 200                 # ≤200 владельцев в мире
)
```

Все три условия — обязательные. Каждый сигнал по отдельности обманывается, в
комбо отсекают ложноположительные:
- без `price` — обскурный треш проходит
- без `num_for_sale` — массовые дорогие лимитки проходят (Daft Punk Discovery $400)
- без `have` — свежий хайп проходит (Glass Beams Mahal на пике)

**Пороги в коде (`Backend/app/services/discogs.py`):**
```python
COLLECTIBLE_MIN_PRICE_USD = 100.0
COLLECTIBLE_MAX_FOR_SALE = 3
COLLECTIBLE_MAX_HAVE = 200
```
Меняются константой без миграции.

**Визуал (Mobile):** emerald `#3F8E6F → #1F5C4D → #0E2E26` (драгоценный камень).
`CollectibleAura` — двухслойный pulse 6s (deep halo + close border). Медленнее
limited/hot — «контейнерная ценность», не суетливая.

**Реальные числа:** 5 (2.7%). Список (для калибровки):
- $500 Tropical Fuck Storm + King Gizzard — Satanic Slumber Party (LIM)
- $377 Glass Beams — Mahal japanese (LIM)
- $230 Masayoshi Takanaka — The Rainbow Goblins 2021 Japan (HOT)
- $150 Mei Ehara — Ampersands 2025 Japan
- $121 Tim Maia — Tim Maia 1985 Brazil

---

### 🟣 Лимитка (`is_limited`)
**Что значит:** есть структурный маркер в `formats[].descriptions` от Discogs.

**Логика:**
```python
is_limited = any token in formats[].descriptions, where token in:
    "Test Pressing", "Promo", "Promotional", "Limited Edition",
    "Numbered", "Ltd. Ed.", "White Label"
```
Без новых API-вызовов — данные уже в release response.

**Визуал:** cold platinum violet `#C0C0D8 → #6B4DCE → #2A1F4E`. PulseAura 4s.

**Реальные числа:** 75 (40%) — много, потому что много современных «Limited
Edition» переизданий.

---

### 🟠 Популярно (`is_hot`)
**Что значит:** высокий спрос на Discogs. Want/have ratio — индикатор «культовости».

**Логика:**
```python
is_hot = community.have >= 100 AND (community.want / community.have) >= 1.5
```

**Пороги в коде:**
```python
HOT_WANT_HAVE_RATIO = 1.5
HOT_MIN_HAVE = 100
```

**Контекстное скрытие:** в личной коллекции HOT не показывается — спрос
нерелевантен когда уже владеешь. В поиске / вишлисте / профиле / детали — видно.

**Визуал:** hot ember `#FFB347 → #FF5E3A → #B22222`. PulseAura 2s + heat-haze
halo на обложке.

**Реальные числа:** 15 (8%).

---

## Закрытый тир: 1-й пресс (`is_first_press`)

Тир был открыт, потом закрыт. Колонка в БД оставлена (всегда `False`) для
безопасного rollback.

**Эволюция:**
1. **v1**: `release.id == master.main_release_id` → 22 пластинки (= то, что
   сейчас называется «Канон»)
2. **v2**: добавили требование `release.year == master.year` → ещё меньше
3. **v3 (Решение 5)**: разрешили fallback через notes/formats → ~25 шт.
4. **v4 (развязка от canon)**: `year_matches AND ≥2 версий` без требования canon
   → 93 шт. (49% коллекции)

**Почему закрыли:** на 188 записях было 93 first_press = половина коллекции.
Слишком много, тир теряет смысл. Главная причина: **Discogs API не позволяет
надёжно определить первопресс** — для этого нужны:
- Matrix/Runout коды (плохо парсятся)
- Label variations (визуальный осмотр)
- Особенности обложки / вкладыши (визуально)

«Year matches master.year» даёт false positives для каждого UK/EU/US пресса
одного и того же года.

---

## Архитектура (Backend)

### `Backend/app/services/discogs.py`

**`_compute_rarity_flags(release_data, master_data, master_versions_count, price_stats)`**
- Принимает все данные на вход (parsed release, master, кол-во версий мастера, marketplace stats)
- Возвращает dict `{is_first_press, is_canon, is_collectible, is_limited, is_hot}`
- `is_first_press` всегда `False` (тир закрыт)

**`get_release(release_id)`**
- Параллельно дёргает: `_get_price_stats`, `get_master`, `_get_master_versions_count`
- Все три кэшируются в Redis
- Передаёт всё в `_compute_rarity_flags`

**`_get_master_versions_count(master_id)`**
- Один лёгкий запрос `/masters/{id}/versions?per_page=1`
- Берёт `pagination.items`
- Кэшируется на `TTL_MASTER_VERSIONS`

### `Backend/app/api/records.py`

**`GET /masters/{id}/versions` enrichment**
- `is_canon` вычисляется on-the-fly (один кэшированный `get_master`)
- `is_limited` парсится из строки `format` каждой версии
- `is_collectible` и `is_hot` — только из локальной БД (для виденных релизов).
  Per-version marketplace stats = слишком дорого (50 запросов на список)

### Модель и миграции
- `Record.is_canon`, `Record.is_collectible` — Boolean колонки
- `is_first_press` колонка остаётся для backward compat
- Миграции: `20260429_canon_flag`, `20260501_collectible`

### Backfill
- `Backend/scripts/backfill_rarity_flags.py`
- Пройти по всем записям, инвалидировать Redis-кэш, перезапросить
- Запуск: `docker compose ... exec api python -m scripts.backfill_rarity_flags --delay 5`
- ~6s на запись из-за Discogs rate limiter

---

## Архитектура (Mobile)

### `Mobile/components/RarityAura.tsx`
- `RARITY_TIERS` — токены 4 тиров (палитра, edge-градиент, цвета, mood)
- `RarityTier = 'canon' | 'collectible' | 'limited' | 'hot'` (без first_press)
- Примитивы анимаций:
  - `CanonBorderGlow` — двойная анимированная рамка
  - `CollectibleAura` — двухслойный emerald pulse 6s
  - `PulseAura` — для limited/hot
  - `HeatHaze` — внутри обложки для hot
- Public API: `RarityAura` обёртка, `TierCoverEffects`, `TierLabel`, `TierFeatureBlock`

**`pickRarityTier(flags, context)`** — приоритет: `collectible → canon → limited → hot`.

**`allRarityTiers(flags)`** — на детальной странице, без фильтрации контекста.

### Где используется
- `Mobile/components/RecordCard.tsx` — обёртка карточки (list + grid + compact)
- `Mobile/components/VersionCard.tsx` — карточка версии в master/[id]/versions
- `Mobile/app/record/[id].tsx` — секция «Особенности»

### RarityFlags типы
- `is_first_press`, `is_canon`, `is_collectible`, `is_limited`, `is_hot` —
  все опциональные boolean. `is_first_press` оставлен в типах для backward compat
  (бэк всегда возвращает `false`).

---

## Финальная статистика на тестовой коллекции (188 пластинок)

```
1-й пресс:       0   (тир закрыт)
Канон:          22   (12%)
Коллекционка:    5   (~3%)
Лимитка:        75   (40%)
Популярно:      15   (8%)
Без флагов:     ~85
```

Один релиз может иметь несколько флагов одновременно (например, `canon + limited`).

---

## Открытые вопросы / возможные итерации

### 1. «Свежая дорогая лимитка» vs «Историческая редкость»
Daft Punk Discovery (Interstella 555 reissue 2024) — $400, 1554 владельца,
15 копий на маркете. Не проходит порог `have ≤ 200`, остаётся только Лимитка.

User считает, что её стоит выделить как Коллекционку. Но это **другой тип
редкости** — свежий хайп, не историческая ценность. Tim Maia 1985 ($121,
~50 владельцев) — это постоянная редкость, цена будет только расти.

Варианты на будущее:
- **A)** Оставить строго: Daft Punk = Лимитка (текущее состояние)
- **B)** Ослабить `have ≤ 2000` — смешает «настоящие» и «хайп»
- **C)** Завести 5-й тир «Hyped Limited» для дорогой лимитки с большой want/have

### 2. Калибровка порогов
Если 5 коллекционок мало:
- Снизить `COLLECTIBLE_MIN_PRICE_USD` со 100 до 80 → ~8-10 записей
- Поднять `COLLECTIBLE_MAX_FOR_SALE` с 3 до 5 → ~7-8 записей

Без миграции — просто константы в коде.

### 3. Что Discogs **не даёт** (нельзя реализовать):
- Тираж выпуска (`qty` ≠ это диски в упаковке)
- Структурный флаг «first pressing»
- Stamper number (только в шумном Matrix/Runout)
- Withdrawn/Cancelled статус (только в свободном `notes`)

---

## Файлы (текущее состояние)

**Backend:**
- `Backend/app/services/discogs.py` — `_compute_rarity_flags`, `_get_master_versions_count`, константы порогов
- `Backend/app/models/record.py` — 4 boolean колонки
- `Backend/app/schemas/record.py` — `RecordResponse`, `RecordBrief`, `MasterVersion` с флагами
- `Backend/app/schemas/profile.py` — `PublicProfileRecord` с флагами
- `Backend/app/api/records.py` — маппинг при создании Record + enrichment в `/masters/{id}/versions`
- `Backend/app/api/profile.py` — `_record_to_public` пробрасывает флаги
- `Backend/alembic/versions/20260429_add_record_rarity_flags.py`
- `Backend/alembic/versions/20260429_add_is_canon_flag.py`
- `Backend/alembic/versions/20260501_add_is_collectible_flag.py`
- `Backend/scripts/backfill_rarity_flags.py`

**Mobile:**
- `Mobile/components/RarityAura.tsx` — токены тиров, примитивы анимаций, public API
- `Mobile/components/RecordCard.tsx` — обёртка (compact/list/expanded)
- `Mobile/components/VersionCard.tsx` — карточка версии
- `Mobile/components/RecordGrid.tsx` — пробрасывает `rarityContext`
- `Mobile/app/record/[id].tsx` — секция «Особенности»
- `Mobile/app/(tabs)/collection.tsx` — `rarityContext='collection'/'wishlist'`
- `Mobile/app/folder/[id].tsx` — `rarityContext='collection'`
- `Mobile/lib/types.ts` — поля `is_canon`, `is_collectible` etc. в `VinylRecord`, `MasterVersion`, `PublicProfileRecord`

---

## Verification

```bash
# Backend
ssh deploy@85.198.85.12 'cd ~/vertushka && bash Вертушка/Backend/scripts/deploy.sh'

# Прогнать backfill после изменений порогов / логики
ssh deploy@85.198.85.12 'cd ~/vertushka/Вертушка/Backend && \
  docker compose -f docker-compose.prod.yml exec -d -e PYTHONPATH=/app api \
  sh -c "python -m scripts.backfill_rarity_flags --delay 5 > /tmp/backfill.log 2>&1"'

# Проверить результат backfill
ssh deploy@85.198.85.12 'cd ~/vertushka/Вертушка/Backend && \
  docker compose -f docker-compose.prod.yml exec -T api \
  sh -c "grep -E Готово /tmp/backfill.log"'

# Открыть в Mobile (Expo Go)
cd Mobile && npx expo start --clear
```
