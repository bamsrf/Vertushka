/**
 * Даты с бэкенда — всегда UTC. Сейчас API отдаёт их с офсетом (`Z`/`+00:00`),
 * но старые ответы, кэш и второстепенные эндпоинты могут прислать naive ISO
 * (`2026-09-08T12:00:00`), который Hermes на iOS и Android парсит как
 * ЛОКАЛЬНОЕ время — «минуту назад» в Москве превращается в «3 ч назад»
 * (BUGS A14). Naive строку трактуем как UTC, остальное — как есть.
 */
const NAIVE_ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

export function parseServerDate(iso: string): Date {
  return new Date(NAIVE_ISO_RE.test(iso) ? `${iso}Z` : iso);
}
