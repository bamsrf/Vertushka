/// <reference types="jest" />
/**
 * Ретрай обложек (lib/coverRetry): ошибка → бэкофф → `r=N` с прежним cacheKey
 * → прямой внешний URL → failed; сторож по времени; onLoad всё гасит.
 */
import React from 'react';
import renderer, { act } from 'react-test-renderer';
import {
  useCoverSource,
  withRetryParam,
  RETRY_DELAYS_MS,
  COVER_WATCHDOG_MS,
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
  expect(h.state.failed).toBe(true);
});

test('без фолбэка (или фолбэк == uri) после ретраев сразу failed', () => {
  const h = mount(DIRECT, DIRECT);
  for (const delay of RETRY_DELAYS_MS) {
    act(() => h.state.onError({ error: 'x' }));
    act(() => { jest.advanceTimersByTime(delay); });
  }
  act(() => h.state.onError({ error: 'x' }));
  act(() => { jest.advanceTimersByTime(0); });
  expect(h.state.failed).toBe(true);
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
