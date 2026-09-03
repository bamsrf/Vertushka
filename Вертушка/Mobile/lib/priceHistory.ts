/**
 * summarizePriceHistory — выжимка из точек GET /records/{id}/price-history.
 *
 * Дельту раньше не считал никто: PriceSparkline выводил first/current только
 * чтобы выбрать цвет линии, а в шапке показывал «сейчас X · мин. Y». Вопрос
 * «насколько изменилась» оставался без ответа на всех экранах, хотя обе цифры
 * лежали в данных.
 *
 * Два потребителя с разной плотностью: шапка сворачиваемого графика в радаре и
 * (Волна D) строка на карточке пластинки. Гейт «есть что сказать» — общий,
 * поэтому живёт здесь, а не в компонентах.
 */
import { PriceHistoryPoint } from './types';

/**
 * Ниже этого движения показывать нечего. Обходы магазинов дневные, разброс в
 * пару процентов — это шум округлений и смена того, какой магазин сейчас самый
 * дешёвый, а не история цены.
 */
export const SIGNIFICANT_PCT = 5;

/**
 * Точка старше недели значит, что листинги этой пластинки не шевелились: либо
 * пресса нет в наличии, либо цена стоит. Слово «сейчас» на таких данных врёт —
 * ровно этим и врал график на карточке.
 */
export const STALE_AFTER_DAYS = 7;

const DAY_MS = 24 * 60 * 60 * 1000;

export interface PriceHistorySummary {
  /**
   * Цена, с которой сравниваем: живая цена маркета, если её передали, иначе
   * последняя записанная точка. Раньше здесь всегда лежала последняя точка —
   * и дельта отвечала на вопрос «как изменилась цена к моменту последней
   * записи», хотя читалась как «как изменилась к сейчас». На пластинке, где
   * запись оборвалась на пике 4 990 ₽, а магазин уже продаёт за 3 352 ₽, блок
   * показывал рост +48,9% прямо над ценой, от которой этот рост считался.
   */
  current: number;
  /** Последняя ЗАПИСАННАЯ точка — ею заканчивается кривая на графике. */
  lastRecorded: number;
  /** current взят из живой цены маркета, а не из истории. */
  usesLivePrice: boolean;
  /** На сколько процентов текущая цена выше минимума окна. 0 — мы у дна. */
  vsLowPct: number;
  first: number;
  deltaRub: number;
  /** Знаковый процент, одна десятая. */
  deltaPct: number;
  low: number;
  /** ISO-дата первой точки окна — база, от которой считается дельта. */
  firstDate: string;
  /** ISO-дата последней точки (YYYY-MM-DD). */
  lastDate: string;
  staleDays: number;
  isStale: boolean;
  /** Гейт «есть что сказать»: движение заметное и данные не протухли. */
  isSignificant: boolean;
  pointsCount: number;
}

/** Полночь UTC сегодняшнего дня — точки приходят с дневной гранулярностью. */
const todayUtcMs = (): number => {
  const now = new Date();
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
};

export function summarizePriceHistory(
  points: PriceHistoryPoint[],
  /** Живая цена маркета (самое дешёвое предложение сейчас), если известна. */
  livePrice?: number | null,
): PriceHistorySummary | null {
  const priced = points.filter(
    (p): p is PriceHistoryPoint & { min_price_rub: number } => p.min_price_rub != null,
  );
  if (priced.length === 0) return null;

  const values = priced.map((p) => p.min_price_rub);
  const first = values[0];
  const lastRecorded = values[values.length - 1];
  const live = typeof livePrice === 'number' && Number.isFinite(livePrice) && livePrice > 0
    ? livePrice
    : null;
  const current = live ?? lastRecorded;
  const firstDate = priced[0].date;
  const lastDate = priced[priced.length - 1].date;

  const deltaRub = current - first;
  // first приходит из той же выборки, что и current, и отфильтрован по
  // price_rub IS NOT NULL — нулём быть не может, но делим защищённо: цена 0 в
  // распарсенном листинге дешевле обработать здесь, чем ловить Infinity в UI.
  const deltaPct = first > 0 ? Math.round((deltaRub / first) * 1000) / 10 : 0;

  const lastMs = Date.parse(`${lastDate}T00:00:00Z`);
  const staleDays = Number.isNaN(lastMs)
    ? 0
    : Math.max(0, Math.round((todayUtcMs() - lastMs) / DAY_MS));
  const isStale = staleDays > STALE_AFTER_DAYS;

  const low = Math.min(...values, current);

  return {
    current,
    lastRecorded,
    usesLivePrice: live != null,
    vsLowPct: low > 0 ? Math.round(((current - low) / low) * 1000) / 10 : 0,
    first,
    deltaRub,
    deltaPct,
    low,
    firstDate,
    lastDate,
    staleDays,
    isStale,
    // Живая цена не протухает по определению: слово «сейчас» на ней честно,
    // даже если последняя ЗАПИСЬ в истории месячной давности.
    isSignificant: Math.abs(deltaPct) >= SIGNIFICANT_PCT && (live != null || !isStale),
    pointsCount: priced.length,
  };
}
