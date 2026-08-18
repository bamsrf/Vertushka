/**
 * Выбор «показательной» пластинки для подсказок карточки релиза.
 *
 * Четыре подсказки — ярлыки, цвет винила, цена магазина, другие версии —
 * объясняют то, что видно только внутри карточки. Из «Как это работает»
 * открыть их было нельзя: экран отправлял в коллекцию с подписью «открой
 * любую пластинку с ярлыком», то есть перекладывал поиск примера на человека,
 * который как раз пришёл посмотреть, как оно выглядит.
 *
 * Поэтому ищем пример сами — и предпочитаем ОДИН релиз, где сошлось всё
 * сразу: тогда четыре подсказки объясняют одну и ту же карточку, а не гоняют
 * по разным. Ищем в том, что у человека уже есть (коллекция и вишлист):
 * своя пластинка понятнее любой витринной.
 */
import type { CoachMarkKey } from './coachMarks';
import { useCollectionStore } from './store';
import type { VinylRecord } from './types';

/** Какое свойство пластинки нужно каждой подсказке, чтобы ей было что объяснять. */
const FEATURE_BY_KEY: Partial<Record<CoachMarkKey, (r: VinylRecord) => boolean>> = {
  'vinyl-color': (r) => Boolean(r.display_vinyl_color ?? r.vinyl_color_raw),
  // Ровно те же флаги, что читает allRarityTiers в RarityAura.
  'rarity-tiers': (r) => Boolean(r.is_collectible || r.is_limited || r.is_hot),
  'other-versions': (r) => Boolean(r.discogs_master_id),
  // Офферы приезжают отдельным запросом, но их число бэк кладёт прямо в
  // запись — этого хватает, чтобы не открыть карточку с пустым блоком.
  'offer-price': (r) => (r.price_offers_count ?? 0) > 0,
  market: (r) => (r.price_offers_count ?? 0) > 0,
};

export const isRecordScopedKey = (key: CoachMarkKey) => key in FEATURE_BY_KEY;

/**
 * Выбранный пример держим на всю сессию: человек, который подряд открывает
 * «ярлыки», «цвет винила» и «другие версии», должен видеть одну и ту же
 * пластинку, иначе объяснения не складываются в целую карточку.
 */
let cachedId: string | null = null;

function candidates(): VinylRecord[] {
  const { collectionItems, wishlistItems } = useCollectionStore.getState();
  return [
    ...collectionItems.map((i) => i.record),
    ...wishlistItems.map((i) => i.record),
  ].filter(Boolean);
}

const featureCount = (record: VinylRecord) =>
  Object.values(FEATURE_BY_KEY).filter((has) => has?.(record)).length;

/**
 * Пластинка, на которой подсказку есть смысл показывать. null — примера не
 * нашлось, и звать в карточку незачем.
 */
export function pickDemoRecordId(key: CoachMarkKey): string | null {
  const needed = FEATURE_BY_KEY[key];
  if (!needed) return null;

  const pool = candidates();
  // Прошлый выбор годится — берём его, чтобы подсказки не разбредались.
  const cached = cachedId ? pool.find((r) => r.id === cachedId) : undefined;
  if (cached && needed(cached)) return cached.id;

  let best: VinylRecord | null = null;
  let bestScore = 0;
  for (const record of pool) {
    if (!needed(record)) continue;
    const score = featureCount(record);
    if (score > bestScore) {
      best = record;
      bestScore = score;
    }
  }
  if (!best) return null;
  cachedId = best.id;
  return best.id;
}
