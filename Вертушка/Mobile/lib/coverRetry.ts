/**
 * Ретрай загрузки обложки для expo-image — сам он не ретраит: один onError, и
 * ячейка остаётся с blurhash-заглушкой до ремаунта.
 *
 * Зачем это нужно именно обложкам. Незазеркаленная обложка идёт через мост
 * `/covers/{id}.jpg` (см. bridge_cover_url на бэке): первый заход — 302 на
 * внешний оригинал (из РФ i.discogs.com часто не отвечает) и фоновое
 * зеркалирование, второй заход через секунду-две уже отдаёт файл с нашего
 * диска. Плюс холодный экран из десятков промахов упирается в
 * limit_req covers_fallback (10 r/s, burst 40) — хвост получает 429, и ему
 * тоже нужна вторая попытка.
 *
 * Сторожевой таймер: OkHttp у RN собран без таймаутов (connect/read = 0), и
 * запрос к недоступному хосту висит до исчерпания SYN-ретраев ядра (~2 мин на
 * Android). За это время Glide держит поток занятым, и соседние обложки тоже
 * не грузятся. Если за COVER_WATCHDOG_MS нет ни onLoad, ни onError — считаем
 * попытку проваленной и меняем source: expo-image отменяет старый запрос.
 *
 * Попытки: исходный URL → ещё RETRY_DELAYS_MS.length раз с `r=N` (иначе
 * expo-image не перезапустит одинаковый source; cacheKey остаётся исходным,
 * чтобы disk-кэш не дробился) → fallbackUri (прямой внешний URL), если он
 * задан и отличается → failed.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ImageErrorEventData, ImageSource } from 'expo-image';

export const RETRY_DELAYS_MS = [1500, 4000] as const;
export const COVER_WATCHDOG_MS = 12000;

const FALLBACK_STEP = RETRY_DELAYS_MS.length + 1;
const FAILED_STEP = FALLBACK_STEP + 1;

export interface CoverSourceState {
  source: ImageSource | undefined;
  failed: boolean;
  onLoad: () => void;
  onError: (event?: ImageErrorEventData) => void;
}

export function withRetryParam(uri: string, attempt: number): string {
  if (attempt <= 0) return uri;
  const sep = uri.includes('?') ? '&' : '?';
  return `${uri}${sep}r=${attempt}`;
}

export function logCoverError(uri: string, message: string | undefined, step: number): void {
  if (!__DEV__) return;
  console.warn(`[cover] попытка ${step + 1} не удалась: ${uri} — ${message ?? 'без сообщения'}`);
}

function buildSource(
  uri: string | undefined,
  fallbackUri: string | undefined,
  step: number
): ImageSource | undefined {
  if (!uri || step >= FAILED_STEP) return undefined;
  if (step === FALLBACK_STEP) return fallbackUri ? { uri: fallbackUri } : undefined;
  if (step === 0) return { uri };
  return { uri: withRetryParam(uri, step), cacheKey: uri };
}

function nextStep(step: number, uri: string, fallbackUri: string | undefined): number {
  const next = step + 1;
  if (next < FALLBACK_STEP) return next;
  const canFallback = Boolean(fallbackUri) && fallbackUri !== uri;
  if (next === FALLBACK_STEP) return canFallback ? FALLBACK_STEP : FAILED_STEP;
  return FAILED_STEP;
}

export function useCoverSource(uri: string | undefined, fallbackUri?: string): CoverSourceState {
  const [step, setStep] = useState(0);
  const settledRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const advance = useCallback(
    (delayMs: number) => {
      if (!uri) return;
      clearTimer();
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        setStep((s) => nextStep(s, uri, fallbackUri));
      }, delayMs);
    },
    [uri, fallbackUri, clearTimer]
  );

  // Новый URL — новая история попыток.
  useEffect(() => {
    settledRef.current = false;
    setStep(0);
    return clearTimer;
  }, [uri, clearTimer]);

  // Сторожевой таймер на каждую живую попытку.
  useEffect(() => {
    if (!uri || settledRef.current || step >= FAILED_STEP) return;
    advance(COVER_WATCHDOG_MS);
    return clearTimer;
  }, [uri, step, advance, clearTimer]);

  const onLoad = useCallback(() => {
    settledRef.current = true;
    clearTimer();
  }, [clearTimer]);

  const onError = useCallback(
    (event?: ImageErrorEventData) => {
      if (!uri || settledRef.current) return;
      logCoverError(uri, event?.error, step);
      const delay = step < RETRY_DELAYS_MS.length ? RETRY_DELAYS_MS[step] : 0;
      advance(delay);
    },
    [uri, step, advance]
  );

  const source = useMemo(() => buildSource(uri, fallbackUri, step), [uri, fallbackUri, step]);
  return { source, failed: step >= FAILED_STEP, onLoad, onError };
}
