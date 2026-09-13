/**
 * Жест-подсказка формой «нудж»: коротко двигаем саму строку, чтобы стало
 * видно, что она двигается. Правила показа — в lib/useGestureHintGate.ts,
 * каталог — в lib/gestureHints.ts.
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
 * ВАЖНО про `performed`: это обычная JS-функция, вызывать из ворклета через
 * `runOnJS`. Состояние жеста живёт в AsyncStorage, с UI-потока туда не
 * дотянуться.
 */
import { useCallback, useEffect, useRef } from 'react';
import { useIsFocused } from 'expo-router';
import {
  Easing,
  cancelAnimation,
  withDelay,
  withSequence,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

import { useReduceMotion } from './useAnimationGate';
import { useGestureHintGate } from './useGestureHintGate';
import { GestureHintKey, getGestureHint } from './gestureHints';

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
  // Фокус спрашиваем здесь: нудж всегда живёт внутри экрана, а гейт общий и
  // про навигацию ничего не знает (см. его комментарий к `enabled`).
  const focused = useIsFocused();
  const reduceMotion = useReduceMotion();
  const { armed, performed, finish } = useGestureHintGate(key, {
    enabled: enabled && focused,
  });

  /** Двигал ли translation именно ЭТОТ хук — чтобы гасить только своё. */
  const owns = useRef(false);

  useEffect(() => {
    if (!armed) return;

    const base = distance ?? getGestureHint(key).distance ?? 0;
    if (!base) return;
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

    return () => {
      // Экран ушёл посреди нуджа — снимаем анимацию и возвращаем строку на
      // место. Иначе она осталась бы сдвинутой в переиспользованной ячейке
      // списка, и человек увидел бы «сломанную» вёрстку на другой строке.
      if (owns.current) {
        owns.current = false;
        cancelAnimation(translation);
        translation.value = 0;
      }
    };
  }, [armed, distance, key, reduceMotion, translation]);

  // Нудж отыграл — отпускаем слот-владение в гейте. Отдельным эффектом, чтобы
  // не завязывать снятие анимации на тот же таймер.
  useEffect(() => {
    if (!armed) return;
    const total =
      (OUT_MS + HOLD_MS + BACK_MS) * (reduceMotion ? REDUCED_FACTOR : 1);
    const timer = setTimeout(finish, total);
    return () => clearTimeout(timer);
  }, [armed, reduceMotion, finish]);

  const performedAndRelease = useCallback(() => {
    // Нудж и палец на одной shared value: как только человек тронул строку,
    // подсказка перестаёт быть нашей — снимаем владение, чтобы
    // размонтирование не сбросило в ноль то, что сейчас держит палец.
    owns.current = false;
    performed();
  }, [performed]);

  return { performed: performedAndRelease };
}
