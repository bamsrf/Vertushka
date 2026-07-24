/**
 * Префетч-кэш первой страницы версий мастер-релиза.
 *
 * Зачем: мастер-экран и так запрашивал версии — но с per_page=1, только ради
 * счётчика «Все версии (N)». Ключ кэша на бэке включает per_page, поэтому такой
 * запрос грел БЕСПОЛЕЗНУЮ запись (p1:pp1), а тап по «Все версии» начинал всё
 * с нуля: юзер смотрел на спиннер, пока бэк заново собирал pp50.
 *
 * Теперь мастер-экран просит сразу pp50 (total в ответе тот же, счётчик не
 * страдает) и кладёт результат сюда. Экран версий на маунте рисует его мгновенно
 * и обновляет в фоне — воспринимаемая задержка при тапе ≈ 0.
 *
 * In-memory и намеренно примитивно: это ускорение перехода, а не источник
 * правды. Переживать перезапуск приложения незачем — за это отвечают Redis
 * и дамп на бэке.
 */
import { MasterVersion } from './types';

interface PrefetchEntry {
  results: MasterVersion[];
  total: number;
  at: number;
}

/** Свежесть префетча. Дольше держать нет смысла: экран версий всё равно
 *  рефетчит в фоне, а несвежий список успел бы разойтись с бэком. */
const TTL_MS = 2 * 60 * 1000;
/** Потолок записей — навигация по мастерам за сессию не должна течь. */
const MAX_ENTRIES = 20;

const cache = new Map<string, PrefetchEntry>();

export function putVersionsPrefetch(
  masterId: string,
  results: MasterVersion[],
  total: number,
): void {
  if (!masterId || results.length === 0) return;
  // Map хранит порядок вставки → первый ключ самый старый.
  if (cache.size >= MAX_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest !== undefined) cache.delete(oldest);
  }
  cache.delete(masterId);
  cache.set(masterId, { results, total, at: Date.now() });
}

export function takeVersionsPrefetch(
  masterId: string,
): { results: MasterVersion[]; total: number } | null {
  const entry = cache.get(masterId);
  if (!entry) return null;
  if (Date.now() - entry.at > TTL_MS) {
    cache.delete(masterId);
    return null;
  }
  return { results: entry.results, total: entry.total };
}
