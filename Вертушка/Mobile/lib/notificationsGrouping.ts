/**
 * Группировка уведомлений и соц-фида в date-bucket секции:
 *   Сегодня · Вчера · На этой неделе · Ранее
 */

export type DateBucket = 'today' | 'yesterday' | 'week' | 'earlier';

export const BUCKET_LABEL: Record<DateBucket, string> = {
  today: 'Сегодня',
  yesterday: 'Вчера',
  week: 'На этой неделе',
  earlier: 'Ранее',
};

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function dateBucket(iso: string, now: Date = new Date()): DateBucket {
  const created = new Date(iso);
  const todayStart = startOfDay(now).getTime();
  const yesterdayStart = todayStart - DAY_MS;
  const weekStart = todayStart - 6 * DAY_MS;
  const createdMs = created.getTime();

  if (createdMs >= todayStart) return 'today';
  if (createdMs >= yesterdayStart) return 'yesterday';
  if (createdMs >= weekStart) return 'week';
  return 'earlier';
}

export interface Section<T> {
  bucket: DateBucket;
  title: string;
  data: T[];
}

const ORDER: DateBucket[] = ['today', 'yesterday', 'week', 'earlier'];

/**
 * Бакетизация по «эффективной дате» (по умолчанию bumped_at ?? created_at), чтобы
 * свежие повторы (occurrences>1) попадали в правильную секцию и всплывали наверх.
 * Внутри секции сортируем по эффективной дате desc.
 */
export function groupByDateBucket<T extends { created_at: string; bumped_at?: string }>(
  items: T[],
  now: Date = new Date(),
  dateOf: (item: T) => string = (item) => item.bumped_at ?? item.created_at,
): Section<T>[] {
  const map = new Map<DateBucket, T[]>();
  for (const item of items) {
    const b = dateBucket(dateOf(item), now);
    const arr = map.get(b) ?? [];
    arr.push(item);
    map.set(b, arr);
  }
  return ORDER
    .filter((b) => (map.get(b)?.length ?? 0) > 0)
    .map((b) => {
      const data = map
        .get(b)!
        .slice()
        .sort((a, c) => new Date(dateOf(c)).getTime() - new Date(dateOf(a)).getTime());
      return { bucket: b, title: BUCKET_LABEL[b], data };
    });
}
