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

/**
 * Поздняя волна: ещё одна попытка через LATE_RETRY_MS после того, как все
 * ближние исчерпаны.
 *
 * Без неё заглушка была вечной, и это главная жалоба по обложкам. Первый
 * заход за незазеркаленной обложкой самозалечивается: nginx не находит файл →
 * get_cover отдаёт 302 и запускает зеркалирование. Скачивание и энкод занимают
 * секунды — то есть картинка появляется ВСКОРЕ ПОСЛЕ того, как ближние попытки
 * (1.5 с и 4 с) уже провалились. Хук уходил в failed навсегда, и плитка висела
 * серой до размонтирования, хотя файл лежал на диске. Ровно то же и при 429 от
 * limit_req, и при отказе по бюджету Discogs — там бесплатная лестница тоже
 * доезжает фоном.
 *
 * Волн две, не бесконечность: мёртвая обложка не должна долбить сервер. Две
 * волны по 20 с покрывают и зеркалирование, и лестницу, и разгрузку очереди.
 */
export const LATE_RETRY_MS = 20000;
export const MAX_LATE_WAVES = 2;

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
  step: number,
  wave: number
): ImageSource | undefined {
  if (!uri || step >= FAILED_STEP) return undefined;
  if (step === FALLBACK_STEP) return fallbackUri ? { uri: fallbackUri } : undefined;
  if (step === 0 && wave === 0) return { uri };
  // `r=` обязателен, иначе expo-image не перезапустит одинаковый source, и
  // поздняя волна была бы пустышкой. Номер волны входит в параметр — у каждой
  // свой URL. cacheKey остаётся исходным: disk-кэш не должен дробиться.
  return { uri: withRetryParam(uri, wave * 10 + step), cacheKey: uri };
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
  const [wave, setWave] = useState(0);
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
    setWave(0);
    return clearTimer;
  }, [uri, clearTimer]);

  // Поздняя волна: зеркалирование/лестница доезжают уже после того, как
  // ближние попытки исчерпаны. Свой таймер, а не общий timerRef: сторожевой
  // эффект на этом шаге не работает, пересекаться нечему.
  useEffect(() => {
    if (!uri || settledRef.current) return;
    if (step < FAILED_STEP || wave >= MAX_LATE_WAVES) return;
    const timer = setTimeout(() => {
      setWave((w) => w + 1);
      setStep(0);
    }, LATE_RETRY_MS);
    return () => clearTimeout(timer);
  }, [uri, step, wave]);

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

  const source = useMemo(
    () => buildSource(uri, fallbackUri, step, wave),
    [uri, fallbackUri, step, wave]
  );
  // failed — «сдались совсем»: показываем заглушку только когда поздние волны
  // тоже вышли. Иначе плитка мигала бы заглушкой между волнами.
  return {
    source,
    failed: step >= FAILED_STEP && wave >= MAX_LATE_WAVES,
    onLoad,
    onError,
  };
}
