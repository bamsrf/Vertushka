/// <reference types="jest" />
/**
 * BUGS A14: naive ISO с бэкенда (без офсета) — это UTC, а не локальное время.
 */
import { parseServerDate } from '@/lib/serverDate';

const UTC_MS = Date.UTC(2026, 8, 8, 12, 0, 5);

test('naive ISO трактуется как UTC', () => {
  expect(parseServerDate('2026-09-08T12:00:05').getTime()).toBe(UTC_MS);
  expect(parseServerDate('2026-09-08T12:00:05.123456').getTime()).toBe(UTC_MS + 123);
  expect(parseServerDate('2026-09-08T12:00').getTime()).toBe(UTC_MS - 5000);
});

test('строки с Z и +00:00 (новый формат API) парсятся как есть', () => {
  expect(parseServerDate('2026-09-08T12:00:05Z').getTime()).toBe(UTC_MS);
  expect(parseServerDate('2026-09-08T12:00:05+00:00').getTime()).toBe(UTC_MS);
  expect(parseServerDate('2026-09-08T15:00:05+03:00').getTime()).toBe(UTC_MS);
});

test('«минуту назад» остаётся минутой при любом офсете устройства', () => {
  const now = Date.now();
  const iso = new Date(now - 60_000).toISOString().replace('Z', '');
  const diffMin = Math.round((now - parseServerDate(iso).getTime()) / 60_000);
  expect(diffMin).toBe(1);
});
