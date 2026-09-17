/// <reference types="jest" />
/**
 * Ретрай обложек (lib/coverRetry): ошибка → бэкофф → `r=N` с прежним cacheKey
 * → прямой внешний URL → поздние волны → failed; сторож по времени; onLoad
 * всё гасит.
 */
import React from 'react';
import renderer, { act } from 'react-test-renderer';
import {
  useCoverSource,
  withRetryParam,
  RETRY_DELAYS_MS,
  COVER_WATCHDOG_MS,
  LATE_RETRY_MS,
  MAX_LATE_WAVES,
  type CoverSourceState,
} from '@/lib/coverRetry';

const MIRROR = 'https://api.example/covers/w/640/123.jpg?v=1';
const DIRECT = 'https://i.discogs.com/abc/h:600/w:600/x.jpeg';

function Probe({ uri, fallback, onState }: {
  uri: string | undefined;
  fallback?: string;
  onState: (s: CoverSourceState) => void;
}) {
  onState(useCoverSource(uri, fallback));
  return null;
}

function mount(uri: string | undefined, fallback?: string) {
  const latest: { state: CoverSourceState | null } = { state: null };
  let tree: renderer.ReactTestRenderer | null = null;
  act(() => {
    tree = renderer.create(
      <Probe uri={uri} fallback={fallback} onState={(s) => { latest.state = s; }} />
    );
  });
  return {
    get state() { return latest.state as CoverSourceState; },
    rerender(nextUri: string | undefined, nextFallback?: string) {
      act(() => {
        tree?.update(
          <Probe uri={nextUri} fallback={nextFallback} onState={(s) => { latest.state = s; }} />
        );
      });
    },
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});


/** Исчерпать ближние попытки: бэкофф + фолбэк. Дальше — только поздние волны.
 *  Считаем не шаги, а факт «источника больше нет»: с фолбэком попыток на одну
 *  больше, и захардкоженная длина уже один раз соврала. */
function exhaustNearAttempts(h: ReturnType<typeof mount>) {
  for (let i = 0; i <= RETRY_DELAYS_MS.length + 2; i += 1) {
    if (h.state.source === undefined) return;
    act(() => h.state.onError({ error: 'x' }));
    act(() => { jest.advanceTimersByTime(RETRY_DELAYS_MS[i] ?? 0); });
  }
  throw new Error('ближние попытки не исчерпались — контракт хука изменился');
}

test('withRetryParam учитывает существующий query', () => {
  expect(withRetryParam('https://a/x.jpg', 0)).toBe('https://a/x.jpg');
  expect(withRetryParam('https://a/x.jpg', 1)).toBe('https://a/x.jpg?r=1');
  expect(withRetryParam('https://a/x.jpg?v=5', 2)).toBe('https://a/x.jpg?v=5&r=2');
});

test('первая попытка — исходный URL без cacheKey', () => {
  const h = mount(MIRROR, DIRECT);
  expect(h.state.source).toEqual({ uri: MIRROR });
  expect(h.state.failed).toBe(false);
});

test('onError → бэкофф → r=N с исходным cacheKey → фолбэк → failed', () => {
  const h = mount(MIRROR, DIRECT);

  act(() => h.state.onError({ error: '429' }));
  expect(h.state.source).toEqual({ uri: MIRROR });
  act(() => { jest.advanceTimersByTime(RETRY_DELAYS_MS[0]); });
  expect(h.state.source).toEqual({ uri: `${MIRROR}&r=1`, cacheKey: MIRROR });

  act(() => h.state.onError({ error: '429' }));
  act(() => { jest.advanceTimersByTime(RETRY_DELAYS_MS[1]); });
  expect(h.state.source).toEqual({ uri: `${MIRROR}&r=2`, cacheKey: MIRROR });

  act(() => h.state.onError({ error: '404' }));
  act(() => { jest.advanceTimersByTime(0); });
  expect(h.state.source).toEqual({ uri: DIRECT });

  act(() => h.state.onError({ error: 'timeout' }));
  act(() => { jest.advanceTimersByTime(0); });
  expect(h.state.source).toBeUndefined();
  // Ещё не failed: впереди поздние волны — зеркало доезжает уже после того,
  // как ближние попытки провалились.
  expect(h.state.failed).toBe(false);
});

test('без фолбэка (или фолбэк == uri) ближние попытки кончаются сразу', () => {
  const h = mount(DIRECT, DIRECT);
  exhaustNearAttempts(h);
  expect(h.state.source).toBeUndefined();
  expect(h.state.failed).toBe(false); // ждём поздние волны
});

test('поздняя волна: через LATE_RETRY_MS попытка повторяется с новым r=', () => {
  // Главный сценарий жалобы: первый заход самозалечивается (302 + фоновое
  // зеркалирование), файл появляется через секунды — то есть уже после того,
  // как ближние попытки провалились. Без поздней волны плитка висела серой.
  const h = mount(MIRROR, DIRECT);
  exhaustNearAttempts(h);
  expect(h.state.source).toBeUndefined();

  act(() => { jest.advanceTimersByTime(LATE_RETRY_MS); });
  expect(h.state.source).toBeDefined();
  // cacheKey исходный — disk-кэш не дробится; URL уникален, иначе expo-image
  // не перезапустил бы одинаковый source.
  expect(h.state.source).toMatchObject({ cacheKey: MIRROR });
  expect((h.state.source as { uri: string }).uri).toContain('r=');
  expect((h.state.source as { uri: string }).uri).not.toBe(MIRROR);
});

test('волны конечны: после MAX_LATE_WAVES наступает failed', () => {
  // Мёртвая обложка не должна долбить сервер бесконечно.
  const h = mount(MIRROR, DIRECT);
  exhaustNearAttempts(h);
  for (let w = 0; w < MAX_LATE_WAVES; w += 1) {
    act(() => { jest.advanceTimersByTime(LATE_RETRY_MS); });
    exhaustNearAttempts(h);
  }
  expect(h.state.failed).toBe(true);
  expect(h.state.source).toBeUndefined();
  // Дальше тишина: новых попыток не появляется.
  act(() => { jest.advanceTimersByTime(LATE_RETRY_MS * 5); });
  expect(h.state.source).toBeUndefined();
});

test('у каждой волны свой URL — иначе вторая волна была бы пустышкой', () => {
  const h = mount(MIRROR, DIRECT);
  exhaustNearAttempts(h);
  act(() => { jest.advanceTimersByTime(LATE_RETRY_MS); });
  const first = (h.state.source as { uri: string }).uri;
  exhaustNearAttempts(h);
  act(() => { jest.advanceTimersByTime(LATE_RETRY_MS); });
  const second = (h.state.source as { uri: string }).uri;
  expect(second).not.toBe(first);
});

test('успех в поздней волне гасит всё: failed не наступает', () => {
  const h = mount(MIRROR, DIRECT);
  exhaustNearAttempts(h);
  act(() => { jest.advanceTimersByTime(LATE_RETRY_MS); });
  act(() => h.state.onLoad());
  act(() => { jest.advanceTimersByTime(LATE_RETRY_MS * 5); });
  expect(h.state.failed).toBe(false);
});

test('сторож: тишина дольше COVER_WATCHDOG_MS перезапускает загрузку', () => {
  const h = mount(MIRROR, DIRECT);
  act(() => { jest.advanceTimersByTime(COVER_WATCHDOG_MS - 1); });
  expect(h.state.source).toEqual({ uri: MIRROR });
  act(() => { jest.advanceTimersByTime(1); });
  expect(h.state.source).toEqual({ uri: `${MIRROR}&r=1`, cacheKey: MIRROR });
});

test('onLoad гасит сторож и последующие onError', () => {
  const h = mount(MIRROR, DIRECT);
  act(() => h.state.onLoad());
  act(() => { jest.advanceTimersByTime(COVER_WATCHDOG_MS * 2); });
  act(() => h.state.onError({ error: 'late' }));
  act(() => { jest.advanceTimersByTime(RETRY_DELAYS_MS[0]); });
  expect(h.state.source).toEqual({ uri: MIRROR });
});

test('смена URL сбрасывает историю попыток', () => {
  const h = mount(MIRROR, DIRECT);
  act(() => h.state.onError({ error: 'x' }));
  act(() => { jest.advanceTimersByTime(RETRY_DELAYS_MS[0]); });
  expect(h.state.source?.cacheKey).toBe(MIRROR);
  const other = 'https://api.example/covers/w/640/999.jpg';
  h.rerender(other);
  expect(h.state.source).toEqual({ uri: other });
});

test('dev-лог ошибки содержит URL и сообщение', () => {
  const h = mount(MIRROR);
  act(() => h.state.onError({ error: 'HTTP 429' }));
  expect(console.warn).toHaveBeenCalledWith(expect.stringContaining(MIRROR));
  expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('HTTP 429'));
});
