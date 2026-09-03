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
  /** Минимум последнего дня с изменением — не обязательно цена «прямо сейчас». */
  current: number;
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
): PriceHistorySummary | null {
  const priced = points.filter(
    (p): p is PriceHistoryPoint & { min_price_rub: number } => p.min_price_rub != null,
  );
  if (priced.length === 0) return null;

  const values = priced.map((p) => p.min_price_rub);
  const first = values[0];
  const current = values[values.length - 1];
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

  return {
    current,
    first,
    deltaRub,
    deltaPct,
    low: Math.min(...values),
    firstDate,
    lastDate,
    staleDays,
    isStale,
    isSignificant: Math.abs(deltaPct) >= SIGNIFICANT_PCT && !isStale,
    pointsCount: priced.length,
  };
}
