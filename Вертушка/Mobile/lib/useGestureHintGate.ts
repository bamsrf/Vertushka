/**
 * Общие правила показа жест-подсказки — без единого слова о том, КАК она
 * выглядит. Правила и каталог — в lib/gestureHints.ts.
 *
 * Зачем отдельно от useGestureNudge. Форм у жест-подсказки две, и они
 * непохожи. Свайп-строку можно подсказать самой строкой: нудж пишет в ту же
 * shared value, что и палец. А свайп «назад» двигает ЭКРАН, и на iOS его
 * везёт нативный стек — своей shared value там нет вовсе. Значит презентация
 * у второй формы своя, а правила («освоил — молчим», «два показа», «одна за
 * запуск», пауза, не поверх контекстной подсказки) обязаны быть общими:
 * иначе две поверхности начнут спорить за внимание и каждая заведёт свою
 * память, как это уже случилось с флагами в marketStore.
 *
 * Гейт отвечает ровно на один вопрос: «показывать прямо сейчас?». Что именно
 * нарисовать — дело вызывающего.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import { analytics } from './analytics';
import { useAuthStore } from './store';
import { useAppForeground } from './useAnimationGate';
import { isAnyCoachSpotlightActive } from './coachSpotlight';
import {
  GestureHintKey,
  getGestureHintRevision,
  isGestureHintSuppressed,
  isGestureSlotTaken,
  loadGestureHintStates,
  markGestureHintShown,
  markGesturePerformed,
  releaseGestureSlot,
  subscribeGestureHints,
  takeGestureSlot,
} from './gestureHints';

/**
 * Пауза перед показом. Экран должен успеть доехать и замереть: подсказка,
 * стартующая одновременно с появлением экрана, сливается с анимацией перехода
 * и читается как рывок вёрстки, а не как приглашение к жесту.
 *
 * 900 мс — та же пауза, что у авто-тизера вишлиста (WishlistListSwipe),
 * проверенная на реальном экране.
 */
export const DWELL_MS = 900;

interface UseGestureHintGateOptions {
  /**
   * Показывать ли вообще: нужная строка, нужный экран И экран в фокусе.
   *
   * Фокус гейт НЕ спрашивает сам намеренно. `useIsFocused` требует контекста
   * экрана и бросает вне его, а одна из форм подсказки — оверлей корневого
   * layout'а, который живёт рядом со `<Stack>`, а не внутри. Хуки нельзя
   * звать по условию, поэтому дешевле спросить фокус там, где он заведомо
   * есть, и сложить его в `enabled`.
   */
  enabled: boolean;
  /** Своя пауза, если экрану нужно больше времени на въезд. */
  dwellMs?: number;
}

export interface GestureHintGate {
  /** Показывать прямо сейчас. */
  armed: boolean;
  /**
   * Жест сделан человеком — гасим навсегда. Из ворклета звать через runOnJS.
   * Идемпотентно: повторные вызовы на каждый пан в БД не ходят.
   */
  performed: () => void;
  /** Подсказка отыграла и убралась сама (по таймеру). */
  finish: () => void;
}

export function useGestureHintGate(
  key: GestureHintKey,
  { enabled, dwellMs = DWELL_MS }: UseGestureHintGateOptions,
): GestureHintGate {
  const userId = useAuthStore((s) => s.user?.id);
  const foreground = useAppForeground();
  const revision = useSyncExternalStore(
    subscribeGestureHints,
    getGestureHintRevision,
    () => 0,
  );

  const [armed, setArmed] = useState(false);
  /** Слот держим мы — вернуть при размонтировании, если не отыграли. */
  const ownsSlot = useRef(false);
  /** Жест уже засчитан в этой сессии. */
  const notedRef = useRef(false);
  /** Подсказка успела показаться — аналитике нужно отделить «освоил после
   *  подсказки» от «знал и так». */
  const shownRef = useRef(false);

  const performed = useCallback(() => {
    setArmed(false);
    ownsSlot.current = false;
    if (notedRef.current || !userId) return;
    notedRef.current = true;
    analytics.gestureHintPerformed(key, shownRef.current);
    void markGesturePerformed(userId, key);
  }, [userId, key]);

  const finish = useCallback(() => {
    setArmed(false);
    ownsSlot.current = false;
  }, []);

  useEffect(() => {
    if (!userId || !enabled || !foreground) return;
    if (armed || notedRef.current) return;
    if (isGestureSlotTaken()) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    (async () => {
      const states = await loadGestureHintStates(userId);
      if (cancelled || isGestureHintSuppressed(states.get(key))) return;

      // Пауза ДО заявки на слот: пока идёт ожидание, слот свободен, и
      // подсказка соседнего экрана не блокируется зря.
      await new Promise<void>((resolve) => {
        timer = setTimeout(resolve, dwellMs);
      });
      if (cancelled) return;

      // Контекстная подсказка на экране — молчим. Две онбординг-штуки разом
      // человек читает как сбой, а не как заботу.
      if (isAnyCoachSpotlightActive()) return;
      if (!takeGestureSlot()) return;
      if (cancelled) {
        releaseGestureSlot();
        return;
      }

      ownsSlot.current = true;
      shownRef.current = true;
      analytics.gestureHintShown(key);
      void markGestureHintShown(userId, key);
      setArmed(true);
    })();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      // Ушли с экрана, не успев показать, — слот возвращаем, иначе запуск
      // останется вообще без подсказки.
      if (ownsSlot.current) {
        ownsSlot.current = false;
        releaseGestureSlot();
      }
    };
  }, [userId, key, enabled, foreground, dwellMs, armed, revision]);

  return { armed, performed, finish };
}
