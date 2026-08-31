# Plan — Achievements Archetypes V3 «Физика звука»

## Концепция

Pure XP-ladder. Каждая открытая ачивка даёт очки по тиру. Сумма очков → уровень
из 10 ступеней «Физика звука» (от **Тишь** до **Первозвук**).

Никаких predicate-правил по конкретным мета, никаких breadth/balance gates,
никаких overlay-специализаций. Юзер копит очки откуда угодно — поощряет пробовать
разные фичи, потому что любая ачивка приближает следующий уровень.

## Очки за тир

```
simple  = 1
notable = 3
rare    = 10
epic    = 30
legend  = 100
```

Геометрическая прогрессия ×3 — каждая ступень тира ощутимо ценнее. Легендарная
видимо «дорогая», но и simple не нули.

**Max-score под текущий каталог** (22s + 11n + 22r + 11e + 5l) = **1105**.

## Лестница уровней

| # | key | label | threshold | flavor | tierKey |
|---|---|---|---:|---|---|
| 0 | `silence` | **Тишь** | 0 | Ты ещё не нажал на play. Но уже пришёл. | simple |
| 1 | `rustle` | **Шорох** | 10 | Игла коснулась. Всё остальное — дело времени. | simple |
| 2 | `echo` | **Эхо** | 30 | Что-то услышанное однажды не уходит. Оно возвращается. | notable |
| 3 | `wave` | **Волна** | 75 | Ты больше не слушаешь музыку. Ты в ней. | notable |
| 4 | `resonance` | **Резонанс** | 150 | Правильная пластинка в правильный момент — это физика, не случайность. | rare |
| 5 | `overtone` | **Обертон** | 275 | Слышишь то, чего нет в нотах. Значит, слух уже другой. | rare |
| 6 | `amplitude` | **Амплитуда** | 450 | Твоя коллекция давит на воздух. Это чувствуют все, кто входит в комнату. | epic |
| 7 | `frequency` | **Частота** | 650 | Ты настроен точнее большинства. Фальшь слышна за три такта. | epic |
| 8 | `tuning_fork` | **Камертон** | 850 | К тебе приходят сверяться. Ты — точка отсчёта. | legend |
| 9 | `primal_sound` | **Первозвук** | 1050 | Было время до тебя. Теперь от тебя считают. | legend |

### Пейсинг
Множитель к предыдущему порогу: 10 → 30 (×3) → 75 (×2.5) → 150 (×2) → 275 (×1.83)
→ 450 (×1.64) → 650 (×1.44) → 850 (×1.31) → 1050 (×1.24). Ранние ступени быстрые
(engagement), поздние медленные (mastery grind).

## Sanity-чек прогрессии

| профиль юзера | примерный score | уровень |
|---|---:|---|
| 5 simple (foundation start) | 5 | Тишь |
| 10 simple | 10 | Шорох |
| 10 simple + 3 notable + 1 rare | 29 | Шорох (почти Эхо) |
| ~20 ачивок, 1 rare | 50 | Эхо |
| Casual 30 ач (15s+8n+5r+2e) | 149 | Волна (почти Резонанс) |
| Solid 40 ач (15s+6n+15r+4e) | 303 | Обертон |
| Hardcore 60 ач (20s+10n+20r+8e+2l) | 690 | Частота |
| Completionist 70/71 + legend | ~1050 | Первозвук |

## API (Mobile/lib/archetype.ts)

```ts
export const TIER_WEIGHT: Record<AchievementTierKey, number>;
export const LEVELS: readonly LevelDef[];

export interface LevelDef {
  key: string;
  label: string;
  threshold: number;
  flavor: string;
  tierKey: AchievementTierKey;
}

export interface ArchetypeInfo {
  key: string;
  label: string;
  flavor: string;
  tierKey: AchievementTierKey;
  score: number;
  currentThreshold: number;
  nextLabel: string | null;
  nextThreshold: number | null;
  pointsToNext: number;
  progressPct: number;       // 0..1
  index: number;             // 0..9
  total: number;             // 10
}

export function computeScore(data: MyAchievementsResponse): number;
export function computeArchetype(data: MyAchievementsResponse): ArchetypeInfo;
```

`computeArchetype` НИКОГДА не возвращает null — у любого юзера есть как минимум
«Тишь».

## UI

### AchievementsHero (Mobile/components/AchievementsHero.tsx)
- Большой counter «X / Y открыто» (анимированный).
- Chip: «УРОВЕНЬ N/10 · **Метка**» (например «УРОВЕНЬ 3/10 · Эхо»).
- **Флейвор-текст уровня** курсивом — ВСЕГДА виден под счётчиком.
- Прогресс-бар: `score / next.threshold` с подписью «142 / 150 XP до «Резонанса»».
- Если max-уровень — «Все ступени пройдены · {score} XP».
- Топ-пин справа (самая редкая) сохранён.

### ArchetypeChip (Mobile/components/ArchetypeChip.tsx)
- Маленький chip с `label` уровня.
- `hideRookie` теперь сравнивает `key === 'silence'` (бывший `rookie`).
- Цвет обводки — по `tierKey` уровня (через `TIER_AURA`).

## Migration notes

- Удалены: 14 predicate-RULES, привязанные к мета-кодам.
- Удалены: ключи `evangelist`, `scientist`, `archivist`, `resident`,
  `polymath`, `cartographer`, `eras_keeper`, `grail_hunter`, `selecta`,
  `gifter`, `searcher`, `quiet_collector`, `melomane`, `rookie`.
- Если где-то стораджем сохранялся `archetype.key` — теперь только `silence`,
  `rustle`, `echo`, `wave`, `resonance`, `overtone`, `amplitude`, `frequency`,
  `tuning_fork`, `primal_sound`.
- ArchetypeChip: `archetype.key === 'rookie'` → `archetype.key === 'silence'`.

## Hero-картинки (опционально)

10 PNG-файлов под уровни в `Mobile/assets/archetypes/{key}.png`. Каждая —
эмалевый-пин-сценка под образ названия (см.
`Design/style-pack-achievements/05_brief/ARCHETYPE_HEROES.md`).
Подключение — после готовности ассетов; пока рендерится только текстовый chip.

## Изменённые файлы

- `Mobile/lib/archetype.ts` — полный rewrite.
- `Mobile/components/AchievementsHero.tsx` — флейвор + прогресс-бар.
- `Mobile/components/ArchetypeChip.tsx` — `hideRookie` сравнение.
- `docs/plans/achievements/PLAN_ACHIEVEMENTS_ARCHETYPES_V3.md` — этот файл.
- `Design/style-pack-achievements/05_brief/ARCHETYPE_HEROES.md` — промпты hero.
