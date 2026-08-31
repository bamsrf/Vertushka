/**
 * Архетипы коллекционера — XP-лестница «Физика звука».
 *
 * V3-rewrite (см. docs/plans/achievements/PLAN_ACHIEVEMENTS_ARCHETYPES_V3.md):
 * - Pure score-based ladder: суммарные очки по тирам открытых ачивок.
 * - 10 уровней (0..9), от «Тишь» до «Первозвук».
 * - У каждого уровня — название, флейвор-текст (постоянно в hero), tier-окрас.
 * - Не зависит от конкретных серий — юзер копит очки откуда угодно, поощряет
 *   пробовать разные фичи.
 *
 * Tier-веса геометрические (x3 ступень):
 *   simple=1, notable=3, rare=10, epic=30, legend=100.
 *
 * Max-score под текущий каталог (22s + 11n + 22r + 11e + 5l) = 1105.
 * Пейсинг уровней — ранний быстрый, поздний медленный (RPG-кривая).
 */
import type { AchievementTierKey, MyAchievementsResponse } from './types';

// ───────────────────────────────────────────────────────────────────────────
// Очки за тир
// ───────────────────────────────────────────────────────────────────────────

export const TIER_WEIGHT: Record<AchievementTierKey, number> = {
  simple: 1,
  notable: 3,
  rare: 10,
  epic: 30,
  legend: 100,
};

// ───────────────────────────────────────────────────────────────────────────
// Лестница уровней «Физика звука»
// ───────────────────────────────────────────────────────────────────────────

export interface LevelDef {
  /** Стабильный ключ (для иконок, аналитики). */
  key: string;
  /** Отображаемое имя уровня. */
  label: string;
  /** Минимальный score для входа на уровень. */
  threshold: number;
  /** Флейвор-текст — постоянно виден в hero блока ачивок. */
  flavor: string;
  /** Цветовая зона — нужна для окрашивания chip-а в стиле тира. */
  tierKey: AchievementTierKey;
}

export const LEVELS: readonly LevelDef[] = [
  {
    key: 'silence',
    label: 'Тишь',
    threshold: 0,
    flavor: 'Ты ещё не нажал на play. Но уже пришёл.',
    tierKey: 'simple',
  },
  {
    key: 'rustle',
    label: 'Шорох',
    threshold: 7,
    flavor: 'Игла коснулась. Всё остальное — дело времени.',
    tierKey: 'simple',
  },
  {
    key: 'echo',
    label: 'Эхо',
    threshold: 15,
    flavor: 'Что-то услышанное однажды не уходит. Оно возвращается.',
    tierKey: 'notable',
  },
  {
    key: 'wave',
    label: 'Волна',
    threshold: 25,
    flavor: 'Ты больше не слушаешь музыку. Ты в ней.',
    tierKey: 'notable',
  },
  {
    key: 'resonance',
    label: 'Резонанс',
    threshold: 50,
    flavor: 'Правильная пластинка в правильный момент — это физика, не случайность.',
    tierKey: 'rare',
  },
  {
    key: 'overtone',
    label: 'Обертон',
    threshold: 100,
    flavor: 'Слышишь то, чего нет в нотах. Значит, слух уже другой.',
    tierKey: 'rare',
  },
  {
    key: 'amplitude',
    label: 'Амплитуда',
    threshold: 250,
    flavor: 'Твоя коллекция давит на воздух. Это чувствуют все, кто входит в комнату.',
    tierKey: 'epic',
  },
  {
    key: 'frequency',
    label: 'Частота',
    threshold: 425,
    flavor: 'Ты настроен точнее большинства. Фальшь слышна за три такта.',
    tierKey: 'epic',
  },
  {
    key: 'tuning_fork',
    label: 'Камертон',
    threshold: 675,
    flavor: 'К тебе приходят сверяться. Ты — точка отсчёта.',
    tierKey: 'legend',
  },
  {
    key: 'primal_sound',
    label: 'Первозвук',
    threshold: 1050,
    flavor: 'Было время до тебя. Теперь от тебя считают.',
    tierKey: 'legend',
  },
] as const;

// ───────────────────────────────────────────────────────────────────────────
// API
// ───────────────────────────────────────────────────────────────────────────

export interface ArchetypeInfo {
  /** Ключ текущего уровня. */
  key: string;
  /** Имя текущего уровня. */
  label: string;
  /** Флейвор-текст текущего уровня. */
  flavor: string;
  /** Tier-окрас для chip-а. */
  tierKey: AchievementTierKey;
  /** Накопленные очки. */
  score: number;
  /** Порог текущего уровня. */
  currentThreshold: number;
  /** Имя следующего уровня (null если max). */
  nextLabel: string | null;
  /** Порог следующего уровня (null если max). */
  nextThreshold: number | null;
  /** Сколько очков до следующего уровня (0 если max). */
  pointsToNext: number;
  /** Прогресс внутри текущего сегмента 0..1 (1 если max). */
  progressPct: number;
  /** Индекс уровня 0..9 — для UI/аналитики. */
  index: number;
  /** Всего уровней (10) — для отображения «6/10». */
  total: number;
}

/**
 * Суммарный XP-score для уровня.
 *
 * Источник истины — `score` из ответа сервера. Локальный пересчёт остаётся
 * только фолбэком для старых версий API.
 */
export function computeScore(data: MyAchievementsResponse): number {
  // Основной путь: считает сервер. Он один видит весь набор — в `series` нет
  // пасхалок, они приходят отдельным запросом, и локальная сумма занижала бы
  // уровень относительно того, о котором приходит push.
  if (typeof data.score === 'number') return data.score;

  // Фолбэк для старых версий API: складываем то, что видно.
  let score = 0;
  for (const series of data.series) {
    for (const item of series.items) {
      if (item.is_unlocked) {
        score += item.xp ?? TIER_WEIGHT[item.tier.key] ?? 0;
      }
    }
  }
  return score;
}

/**
 * Определяет текущий архетип-уровень юзера и сопутствующую инфу.
 *
 * Никогда не возвращает null — у любого юзера есть как минимум «Тишь».
 */
export function computeArchetype(data: MyAchievementsResponse): ArchetypeInfo {
  const score = computeScore(data);

  // Берём самый высокий уровень, чей threshold <= score.
  let idx = 0;
  for (let i = 0; i < LEVELS.length; i++) {
    if (score >= LEVELS[i].threshold) {
      idx = i;
    } else {
      break;
    }
  }

  const current = LEVELS[idx];
  const next = LEVELS[idx + 1] ?? null;
  const span = next ? next.threshold - current.threshold : 0;
  const progressPct = next && span > 0
    ? Math.min(1, Math.max(0, (score - current.threshold) / span))
    : 1;

  return {
    key: current.key,
    label: current.label,
    flavor: current.flavor,
    tierKey: current.tierKey,
    score,
    currentThreshold: current.threshold,
    nextLabel: next?.label ?? null,
    nextThreshold: next?.threshold ?? null,
    pointsToNext: next ? Math.max(0, next.threshold - score) : 0,
    progressPct,
    index: idx,
    total: LEVELS.length,
  };
}
