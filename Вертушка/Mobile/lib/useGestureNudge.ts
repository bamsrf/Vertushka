/**
 * Хук жест-подсказки: коротко двигает саму цель, чтобы стало видно, что она
 * двигается. Правила показа — в lib/gestureHints.ts.
 *
 * Использование (внутри компонента строки):
 *
 *   const dragX = useSharedValue(0);
 *   const { performed } = useGestureNudge('notification-delete', dragX, {
 *     enabled: isFirstRow,
 *   });
 *   const pan = Gesture.Pan().onStart(() => {
 *     runOnJS(performed)();   // жест освоен — больше не подсказываем
 *     ...
 *   });
 *
 * `translation` — ТА ЖЕ shared value, которую двигает палец. Отдельного слоя
 * поверх строки нет намеренно: подсказка должна двигать настоящую цель, иначе
 * она обещает не то, что произойдёт. Заодно это снимает вопрос совмещения —
 * человек, тронувший строку во время нуджа, просто перехватывает управление:
 * присваивание в onUpdate отменяет анимацию само.
 *
 * `enabled` — «эта строка вообще подходит под подсказку». Обычно «строка
 * первая в списке»: дёргать сразу все строки списка нельзя, а нижние человек
 * может и не видеть.
 *
 * ВАЖНО про `performed`: это обычная JS-функция, вызывать из ворклета через
 * `runOnJS`. Не `useCallback`-обёртка вокруг shared value — состояние жеста
 * живёт в AsyncStorage, а туда с UI-потока не дотянуться.
 */
import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { useIsFocused } from 'expo-router';
import {
  Easing,
  cancelAnimation,
  withDelay,
  withSequence,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

import { analytics } from './analytics';
import { useAuthStore } from './store';
import { useAppForeground, useReduceMotion } from './useAnimationGate';
import { isAnyCoachSpotlightActive } from './coachSpotlight';
import {
  GestureHintKey,
  getGestureHint,
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
 * Пауза перед нуджем. Экран должен успеть доехать и замереть: подсказка,
 * стартующая одновременно с появлением списка, сливается с анимацией перехода
 * и читается как рывок вёрстки, а не как приглашение к жесту.
 *
 * 900 мс — та же пауза, что у авто-тизера вишлиста (WishlistListSwipe),
 * проверенная на реальном экране.
 */
const DWELL_MS = 900;

/** Туда. */
const OUT_MS = 420;
/** Подержать на виду — иначе движение читается как дрожание. */
const HOLD_MS = 700;
/** Обратно. Быстрее, чем туда: возврат не несёт информации. */
const BACK_MS = 320;

/**
 * Reduce Motion. Нудж не выключаем: это не декоративная анимация, а
 * единственный способ узнать о жесте — выключить его значит спрятать функцию
 * (тот же довод, по которому VinylSpinner сознательно игнорирует настройку).
 * Но движение делаем скромнее и без ускорений: короче ход, линейная кривая,
 * дольше времени. Резких стартов и пружин здесь нет ни в каком режиме.
 */
const REDUCED_SCALE = 0.55;
const REDUCED_FACTOR = 1.6;

interface UseGestureNudgeOptions {
  enabled: boolean;
  /** Перекрыть дистанцию из каталога — если у поверхности своя геометрия. */
  distance?: number;
}

interface UseGestureNudgeResult {
  /** Жест сделан человеком. Из ворклета вызывать через runOnJS. */
  performed: () => void;
}

export function useGestureNudge(
  key: GestureHintKey,
  translation: SharedValue<number>,
  { enabled, distance }: UseGestureNudgeOptions,
): UseGestureNudgeResult {
  const userId = useAuthStore((s) => s.user?.id);
  const focused = useIsFocused();
  const foreground = useAppForeground();
  const reduceMotion = useReduceMotion();
  const revision = useSyncExternalStore(
    subscribeGestureHints,
    getGestureHintRevision,
    () => 0,
  );

  /** Двигал ли translation именно ЭТОТ хук — чтобы гасить только своё. */
  const owns = useRef(false);
  /** Жест уже засчитан в этой сессии — не ходим в AsyncStorage на каждый пан. */
  const notedRef = useRef(false);
  /** Нудж этой строки уже отыграл — нужно аналитике, чтобы отделить
   *  «освоил после подсказки» от «знал и так». */
  const nudgedRef = useRef(false);

  const performed = useCallback(() => {
    // Нудж и палец на одной shared value: как только человек тронул строку,
    // подсказка перестаёт быть нашей — снимаем владение, чтобы размонтирование
    // не сбросило в ноль то, что сейчас держит палец.
    owns.current = false;
    if (notedRef.current || !userId) return;
    notedRef.current = true;
    analytics.gestureHintPerformed(key, nudgedRef.current);
    void markGesturePerformed(userId, key);
  }, [userId, key]);

  useEffect(() => {
    if (!userId || !enabled || !focused || !foreground) return;
    if (notedRef.current) return;
    if (isGestureSlotTaken()) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    (async () => {
      const states = await loadGestureHintStates(userId);
      if (cancelled || isGestureHintSuppressed(states.get(key))) return;

      // Пауза ДО заявки на слот: пока идёт ожидание, слот свободен, и
      // подсказка соседнего экрана не блокируется зря.
      await new Promise<void>((resolve) => {
        timer = setTimeout(resolve, DWELL_MS);
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

      const base = distance ?? getGestureHint(key).distance;
      const shift = reduceMotion ? base * REDUCED_SCALE : base;
      const factor = reduceMotion ? REDUCED_FACTOR : 1;

      owns.current = true;
      translation.value = withSequence(
        withTiming(shift, {
          duration: OUT_MS * factor,
          easing: reduceMotion ? Easing.linear : Easing.out(Easing.cubic),
        }),
        withDelay(
          HOLD_MS,
          withTiming(0, {
            duration: BACK_MS * factor,
            easing: reduceMotion ? Easing.linear : Easing.in(Easing.cubic),
          }),
        ),
      );

      nudgedRef.current = true;
      analytics.gestureHintShown(key);
      void markGestureHintShown(userId, key);
    })();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      // Экран ушёл посреди нуджа — снимаем анимацию и возвращаем строку на
      // место. Иначе она осталась бы сдвинутой в переиспользованной ячейке
      // списка, и человек увидел бы «сломанную» вёрстку на другой строке.
      if (owns.current) {
        owns.current = false;
        cancelAnimation(translation);
        translation.value = 0;
      }
    };
  }, [
    userId,
    key,
    enabled,
    focused,
    foreground,
    reduceMotion,
    distance,
    translation,
    revision,
  ]);

  return { performed };
}
