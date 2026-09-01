/**
 * Утилиты над MyAchievementsResponse: «последняя открытая»,
 * собирание свежих, подсчёты для архетипа и т. д.
 *
 * Все функции pure — на стороне клиента, без сетевых запросов.
 */
import type {
  AchievementItem,
  AchievementSeriesItem,
  AchievementTierKey,
  MyAchievementsResponse,
} from './types';

const TIER_ORDER: Record<AchievementTierKey, number> = {
  simple: 1,
  notable: 2,
  rare: 3,
  epic: 4,
  legend: 5,
};

/** Все открытые ачивки плоским массивом — без сортировки. */
export function collectUnlocked(
  data: MyAchievementsResponse,
  extraRandom: AchievementItem[] = [],
): AchievementItem[] {
  const result: AchievementItem[] = [];
  for (const series of data.series) {
    for (const item of series.items) {
      if (item.is_unlocked) result.push(item);
    }
  }
  for (const item of extraRandom) {
    if (item.is_unlocked) result.push(item);
  }
  return result;
}

/** Ачивки, открытые одним прогоном evaluator'а, приходят с разницей в
 *  микросекунды. Внутри такой пачки «последняя по времени» — случайная строка
 *  из батча, поэтому время округляем до секунды, а внутри секунды берём
 *  верхнюю по редкости: пачку представляет её самый ценный пин. */
function unlockedBatchSecond(item: AchievementItem): number {
  const t = item.unlocked_at ? Date.parse(item.unlocked_at) : 0;
  return Number.isNaN(t) ? 0 : Math.floor(t / 1000);
}

/** Открытые ачивки от свежих к старым: пачка (секунда) DESC, внутри пачки
 *  тир DESC, дальше точное время DESC. */
export function sortedByFreshness(
  data: MyAchievementsResponse,
  extraRandom: AchievementItem[] = [],
): AchievementItem[] {
  return collectUnlocked(data, extraRandom).sort((a, b) => {
    const sa = unlockedBatchSecond(a);
    const sb = unlockedBatchSecond(b);
    if (sa !== sb) return sb - sa;
    const ta = TIER_ORDER[a.tier.key] || 0;
    const tb = TIER_ORDER[b.tier.key] || 0;
    if (ta !== tb) return tb - ta;
    const da = a.unlocked_at ? Date.parse(a.unlocked_at) : 0;
    const db = b.unlocked_at ? Date.parse(b.unlocked_at) : 0;
    return db - da;
  });
}

/** Последняя открытая ачивка — та, что стоит в гнезде hero. */
export function latestUnlocked(
  data: MyAchievementsResponse,
  extraRandom: AchievementItem[] = [],
): AchievementItem | null {
  return sortedByFreshness(data, extraRandom)[0] || null;
}

export function recentUnlocked(
  data: MyAchievementsResponse,
  limit: number,
  extraRandom: AchievementItem[] = [],
): AchievementItem[] {
  return sortedByFreshness(data, extraRandom).slice(0, limit);
}

/** Список ачивок-series-meta (META_*) — нужны для архетипов. */
export function unlockedMetaCodes(data: MyAchievementsResponse): Set<string> {
  const s = new Set<string>();
  for (const series of data.series) {
    for (const item of series.items) {
      if (item.is_unlocked && item.is_meta) s.add(item.code);
    }
  }
  return s;
}

export function unlockedCodes(data: MyAchievementsResponse): Set<string> {
  const s = new Set<string>();
  for (const series of data.series) {
    for (const item of series.items) {
      if (item.is_unlocked) s.add(item.code);
    }
  }
  return s;
}

export function findSeries(
  data: MyAchievementsResponse,
  key: string,
): AchievementSeriesItem | null {
  return data.series.find((s) => s.key === key) || null;
}
